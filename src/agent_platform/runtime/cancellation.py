"""取消与 worker 领取任务共享环境锁，终态重复请求无副作用。"""
from ..contracts.runs import TERMINAL
from ..contracts.errors import ErrorResponse, PlatformError


def cancel_run(submission, run_id):
    with submission.environments.lock, submission.runs.lock:
        run = submission.runs.get(run_id)
        if run.status in TERMINAL:
            return run
        if run.status == 'running':
            waiting = any(s.kind == 'model' and s.status == 'running' for s in run.steps)
            return submission.runs.update(run_id, cancel_requested=True,
                cancel_phase='waiting_transport' if waiting else None)
        submission.runs.update(run_id, cancel_requested=True)
        run = submission.runs.finish(run_id, 'cancelled')
        submission.environments.release(run_id)
        return run


class CancellationPolicy:
    def __init__(self, runs, run_id):
        self.runs, self.run_id = runs, run_id

    def __call__(self, phase, step_id):
        if phase == 'cleanup':
            return
        run = self.runs.get(self.run_id)
        if run.status == 'running' and run.cancel_requested:
            raise PlatformError(ErrorResponse(code='RUN_CANCELLED', stage='runs.cancel',
                                             message='任务已取消', run_id=self.run_id))
