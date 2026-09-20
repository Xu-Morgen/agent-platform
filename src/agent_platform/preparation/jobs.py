"""可查询、取消和重试的资源准备任务；独立于业务 loop 与契约重试。"""
import asyncio
import threading
from copy import deepcopy
from uuid import uuid4
from .manager import Preparation
from ..contracts.errors import PlatformError, ErrorResponse


class PreparationJobs:
    def __init__(self, catalog):
        self.catalog = catalog
        self.jobs, self.tasks, self.operations = {}, {}, {}
        self.lock = threading.RLock()
        self.loading = asyncio.Lock()

    def start(self, request):
        job_id = 'prep_' + uuid4().hex
        with self.lock:
            self.jobs[job_id] = {'jobId': job_id, 'phase': 'check', 'resource': None, 'error': None}
        def progress(event):
            with self.lock:
                self.jobs[job_id].update(event)
        operation = Preparation(progress=lambda event: progress({**event, 'phase': 'verify' if event['phase'] == 'ready' else event['phase']}))
        self.operations[job_id] = operation
        async def run():
            try:
                # 资源目录发布串行；下载缓存仍有跨进程文件锁。
                async with self.loading:
                    operation.check()
                    resource = await asyncio.to_thread(self.catalog.load, request, operation=operation)
                progress({'phase': 'ready', 'resource': resource.model_dump(mode='json', by_alias=True)})
            except Exception as exc:
                error = exc.error if isinstance(exc, PlatformError) else ErrorResponse(code='DEPENDENCY_ERROR', stage='preparation', message='资源准备失败，请检查声明并重试')
                progress({'phase': 'cancelled' if error.code == 'PREPARATION_CANCELLED' else 'failed', 'error': error.model_dump(mode='json', by_alias=True)})
        self.tasks[job_id] = asyncio.create_task(run())
        return self.get(job_id)

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise PlatformError(ErrorResponse(code='RECORD_NOT_FOUND', stage='preparation', message='准备任务不存在'), 404)
            return deepcopy(self.jobs[job_id])

    def cancel(self, job_id):
        self.get(job_id)
        self.operations[job_id].cancel.set()
        return self.get(job_id)

    async def close(self):
        for operation in self.operations.values(): operation.cancel.set()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
