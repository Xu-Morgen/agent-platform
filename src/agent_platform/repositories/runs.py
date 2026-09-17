"""副本读写；终态只可由 finish 一次提交。"""
from threading import RLock
from uuid import uuid4
from ..contracts.runs import Run, TERMINAL
from ..contracts.errors import ErrorResponse, PlatformError


class RunRepository:
    def __init__(self):
        self.lock = RLock()
        self._items = {}

    def create(self, **values):
        with self.lock:
            run = Run(run_id='run_' + uuid4().hex, **values)
            self._items[run.run_id] = run
            return run.model_copy(deep=True)

    def get(self, run_id):
        with self.lock:
            if run_id not in self._items:
                raise PlatformError(ErrorResponse(code='RECORD_NOT_FOUND', stage='runs',
                                                 message='任务不存在', run_id=run_id), 404)
            return self._items[run_id].model_copy(deep=True)

    def update(self, run_id, **changes):
        with self.lock:
            run = self.get(run_id)
            if run.status in TERMINAL or set(changes) - {'status', 'cancel_requested', 'cancel_phase', 'usage', 'steps'}:
                raise ValueError('终态或固定快照不可更新')
            if 'status' in changes and not (run.status == 'queued' and changes['status'] == 'running'):
                raise ValueError('非法状态流转')
            run = Run.model_validate({**run.model_dump(), **changes})
            self._items[run_id] = run
            return run.model_copy(deep=True)

    def finish(self, run_id, status, *, result=None, error=None):
        with self.lock:
            run = self.get(run_id)
            if run.status in TERMINAL:
                raise ValueError('终态不可覆盖')
            if status not in TERMINAL or (status == 'completed' and run.status != 'running'):
                raise ValueError('非法终态')
            if status == 'completed' and (error or run.cancel_requested):
                raise ValueError('错误或取消任务不可发布成功')
            if status == 'failed' and error is None:
                raise ValueError('失败必须保留原因')
            run = Run.model_validate({**run.model_dump(), 'status': status,
                                      'result': result if status == 'completed' else None, 'error': error, 'cancel_phase': None})
            self._items[run_id] = run
            return run.model_copy(deep=True)
