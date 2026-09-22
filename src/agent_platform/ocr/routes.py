"""桌面模型管理入口；不开放匿名 OCR 识别。"""
import asyncio
from uuid import uuid4

from ..contracts.ocr import OCRImport, OCRSelection, OCRModel, OCRJob
from .adapter import failure


class ModelJobs:
    def __init__(self, repository):
        self.repository = repository
        self.jobs, self.tasks = {}, {}
        self.closed = False

    def start(self, *, directory=None, model_id=None):
        if self.closed or any(not task.done() for task in self.tasks.values()):
            raise failure('OCR_CAPACITY_EXCEEDED', '请等待当前模型导入或验证完成')
        if len(self.jobs) >= 20:
            key = next(iter(self.jobs))
            self.jobs.pop(key)
            self.tasks.pop(key, None)
        job = OCRJob(job_id=uuid4().hex, progress='等待模型检查')
        self.jobs[job.job_id] = job
        async def run():
            try:
                if directory is not None:
                    job.model = await self.repository.import_directory(directory, lambda text: setattr(job, 'progress', text))
                else:
                    from ..contracts.ocr import OCRDiagnostic
                    job.progress = '等待 CPU 工作进程并执行小样例'
                    job.diagnostic = OCRDiagnostic.model_validate(await self.repository.check(model_id))
                job.status, job.progress = 'completed', '完成'
            except asyncio.CancelledError:
                job.status, job.error = 'failed', '应用退出，模型操作已终止'
                raise
            except Exception as exc:
                job.status = 'failed'
                job.error = getattr(getattr(exc, 'error', None), 'message', '模型文件不可访问或导入失败')
        self.tasks[job.job_id] = asyncio.create_task(run())
        return job

    async def close(self):
        self.closed = True
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)


def register_routes(app):
    repository = app.state.ocr
    jobs = app.state.ocr_jobs = ModelJobs(repository)

    @app.get('/api/v1/ocr/models', response_model=list[OCRModel])
    async def models():
        return repository.list()

    @app.get('/api/v1/ocr/selection', response_model=OCRSelection)
    async def selection():
        return repository.selection

    @app.put('/api/v1/ocr/selection', response_model=OCRSelection)
    async def select(value: OCRSelection):
        return repository.select(value)

    @app.post('/api/v1/ocr/import', response_model=OCRJob, status_code=202)
    async def import_model(value: OCRImport):
        return jobs.start(directory=value.directory)

    @app.post('/api/v1/ocr/models/{model_id}/check', response_model=OCRJob, status_code=202)
    async def check(model_id: str):
        repository.get(model_id)
        return jobs.start(model_id=model_id)

    @app.get('/api/v1/ocr/jobs/{job_id}', response_model=OCRJob)
    async def job(job_id: str):
        if job_id not in jobs.jobs:
            raise failure('RECORD_NOT_FOUND', '模型操作记录不存在')
        return jobs.jobs[job_id]
