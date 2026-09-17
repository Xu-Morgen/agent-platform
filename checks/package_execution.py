import asyncio
from dataclasses import replace
from services import setup_app
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.errors import PlatformError
from agent_platform.runtime.context import RunContext
from agent_platform.runtime.boundary import Boundary, current_boundary
from agent_platform.runtime.packages import PackageContext

async def main():
    app, body = setup_app()
    svc = app.state.services.save(ServiceWrite.model_validate(body))
    run = app.state.submission.submit(RunSubmit(service_id=svc.service_id,input={'text':'合成'}))
    snapshot = app.state.services.resolve_current(svc.service_id)
    ctx = RunContext(run.run_id, snapshot, app.state.runs)
    events = []
    token = current_boundary.set(Boundary(observer=lambda phase, step: events.append((phase,step))))
    a = await ctx.invoke_package('echo', {'text':'合成'})
    b = await ctx.invoke_package('second', a)
    assert b.text == a.text and ('package_start','echo') in events
    assert not hasattr(PackageContext(ctx, 'echo', snapshot.packages['echo']), 'invoke_package')
    try: await ctx.invoke_package('echo', {'text':1})
    except PlatformError as exc:
        assert exc.error.stage == 'packages.echo.input' and exc.error.details.package_binding_id == 'echo' and exc.error.details.attempt == 2
    else: raise AssertionError()
    artifact = snapshot.packages['echo']
    class BadOutput:
        def load(self, ref):
            return (lambda *args: {'text':1}) if ref == artifact.manifest.entry else artifact.content.load(ref)
    ctx.snapshot = replace(snapshot, packages={**snapshot.packages, 'echo':replace(artifact, content=BadOutput())})
    try: await ctx.invoke_package('echo', {'text':'合成'})
    except PlatformError as exc:
        assert exc.error.stage == 'packages.echo.output' and exc.error.details.attempt == 3
    else: raise AssertionError()
    current_boundary.reset(token)
    steps = [s for s in app.state.runs.get(run.run_id).steps if s.kind == 'package']
    assert [s.status for s in steps] == ['completed','completed','failed','failed']
    print('两模板包依次组合；包输入/输出错误保留 bindingId/attempt；统一策略入口与包调度隔离通过')

asyncio.run(main())
