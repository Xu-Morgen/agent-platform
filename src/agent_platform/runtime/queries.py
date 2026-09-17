"""只读运行仓储的状态与结果查询。"""
from ..contracts.runs import RunResult
from ..contracts.errors import ErrorResponse, PlatformError


def result_for(runs, run_id):
    run = runs.get(run_id)
    if run.status != 'completed':
        error = run.error or ErrorResponse(code='RESULT_NOT_READY', stage='runs.result',
                                          message='任务尚无可用结果', run_id=run_id)
        error.details.run_status = run.status
        raise PlatformError(error, 409)
    return RunResult(run_id=run_id, instance_id=run.instance_id, result=run.result)
