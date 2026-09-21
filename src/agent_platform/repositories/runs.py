"""副本读写；终态只可由 finish 一次提交。"""
from threading import RLock
from uuid import uuid4
from ..contracts.runs import Run, TERMINAL
from ..contracts.errors import ErrorResponse, PlatformError


class RunRepository:
    def __init__(self, store=None):
        from ..storage import MemoryStore
        self.lock = RLock()
        self.store = store or MemoryStore()
        self._items = {key: Run.model_validate(value) for key, value in self.store.read('runs').items()}
        interrupted = []
        for run in self._items.values():
            if run.status not in TERMINAL:
                error = ErrorResponse(code='APPLICATION_INTERRUPTED', stage='runtime.recovery',
                    message='后端在任务完成前停止；外部操作可能已发生，请核查后重新提交', run_id=run.run_id)
                run.status, run.error, run.cancel_phase = 'failed', error, None
                for step in run.steps:
                    if step.status == 'running':
                        step.status, step.error = 'failed', error.model_copy(deep=True)
                interrupted.append(('runs', run.run_id, run.model_dump(mode='json')))
        if interrupted:
            self.store.write(interrupted)

    def list(self, *, service_id=None, status=None, limit=50, offset=0):
        with self.lock:
            values = sorted(self._items.values(), key=lambda run: (run.created_at, run.run_id), reverse=True)
            values = [run for run in values if (service_id is None or run.service_id == service_id)
                      and (status is None or run.status == status)]
            return [run.model_copy(deep=True) for run in values[offset:offset + limit]]

    def _save(self, run):
        self.store.write([('runs', run.run_id, run.model_dump(mode='json'))])
        self._items[run.run_id] = run

    def create(self, *, files=None, references=(), **values):
        with self.lock:
            run = Run(run_id='run_' + uuid4().hex, **values)
            if files is None:
                self._save(run)
            else:
                with files.lock:
                    documents = files.bindings(references, run.run_id)
                    self.store.write([*documents, ('runs', run.run_id, run.model_dump(mode='json'))])
                    files.accept_bindings(documents)
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
            self._save(run)
            return run.model_copy(deep=True)

    def append_evidence(self, run_id, evidence):
        from ..contracts.knowledge import EvidenceRecord
        from .knowledge import knowledge_error
        evidence = EvidenceRecord.model_validate(evidence)
        with self.lock:
            run = self.get(run_id)
            if run.status != 'running' or run.cancel_requested:
                raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '任务不再接受证据登记')
            if len(run.evidence) >= 100:
                raise knowledge_error('KNOWLEDGE_LIMIT_EXCEEDED', '单任务证据登记超过 100 次上限')
            run.evidence.append(evidence)
            self._save(run)

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
            self._save(run)
            return run.model_copy(deep=True)
