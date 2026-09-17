"""取消与 worker 领取任务共享环境锁，终态重复请求无副作用。"""
from ..contracts.runs import TERMINAL
from ..contracts.errors import ErrorResponse, PlatformError


def cancel_run(submission, run_id):
    with submission.environments.lock, submission.runs.lock:
        run = submission.runs.get(run_id)
        if run.status in TERMINAL:
            return run
        if run.status == 'running':
            raise PlatformError(ErrorResponse(code='CANCEL_NOT_SUPPORTED', stage='runs.cancel',
                                             message='运行任务取消尚未接入', run_id=run_id), 409)
        submission.runs.update(run_id, cancel_requested=True)
        run = submission.runs.finish(run_id, 'cancelled')
        submission.environments.release(run_id)
        return run
