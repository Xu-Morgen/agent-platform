"""合成包验证局部失败扣费、全局累计及满额终态。"""
import asyncio
from services import setup_app
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.errors import PlatformError
from agent_platform.runtime.context import RunContext
from agent_platform.runtime.boundary import Boundary, current_boundary
from agent_platform.runtime.budgets import LoopPolicy

async def case(fail):
    app, body = setup_app()
    body['definition']['configRefs'][0]['values']['loopLimit'] = 1
    body['definition']['budget'] = {'loopLimit': 2, 'tokenLimit': 200}
    svc = app.state.services.save(ServiceWrite.model_validate(body))
    run = app.state.submission.submit(RunSubmit(service_id=svc.service_id, input={'text': '合成'}))
    snapshot = app.state.services.resolve_current(svc.service_id)
    ctx = RunContext(run.run_id, snapshot, app.state.runs)
    boundary = Boundary([LoopPolicy(run.run_id, snapshot, app.state.runs)])
    token = current_boundary.set(boundary)
    try:
        try:
            await ctx.invoke_package('echo', {'text': 1 if fail else '合成'})
        except PlatformError as exc:
            assert fail and exc.error.stage == 'packages.echo.input'
        try:
            await ctx.invoke_package('echo', {'text': '合成'})
        except PlatformError as exc:
            assert exc.error.code == 'LOOP_BUDGET_EXCEEDED'
        else:
            raise AssertionError('局部满额未拒绝')
        await ctx.invoke_package('second', {'text': '合成'})
        await boundary.check('terminal', run.run_id)
        try:
            await ctx.invoke_package('second', {'text': '合成'})
        except PlatformError as exc:
            assert exc.error.code == 'LOOP_BUDGET_EXCEEDED'
        else:
            raise AssertionError('全局满额未拒绝')
        assert app.state.runs.get(run.run_id).usage['loops'] == {
            'global': 2, 'bindings': {'echo': 1, 'second': 1}}
        assert len([s for s in app.state.runs.get(run.run_id).steps if s.kind == 'package']) == 2
    finally:
        current_boundary.reset(token)

asyncio.run(case(True))
asyncio.run(case(False))
print('PASS: 失败不退还；局部/全局拒绝；满额允许终态；被拒绝入口不登记尝试')
