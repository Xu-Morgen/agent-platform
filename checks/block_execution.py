import asyncio
from dataclasses import replace
from services import setup_app
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.errors import PlatformError
from agent_platform.runtime.context import RunContext

async def main():
    app, body = setup_app()
    service = app.state.services.save(ServiceWrite.model_validate(body))
    run = app.state.submission.submit(RunSubmit(service_id=service.service_id,input={'text':'合成'}))
    snapshot = app.state.services.resolve_current(service.service_id)
    ctx = RunContext(run.run_id, snapshot, app.state.runs)
    assert (await ctx.call_block('echo.identity', {'text':'合成'})).text == '合成'
    try: await ctx.call_block('echo.identity', {'text':42})
    except PlatformError as exc: assert exc.error.stage == 'blocks.echo.identity.input'
    else: raise AssertionError()
    original = snapshot.blocks['echo', 'identity']
    class BadContent:
        def load(self, symbol):
            return (lambda value: {'text':42}) if symbol == original.manifest.entry else original.content.load(symbol)
    ctx.snapshot = replace(snapshot, blocks={('echo','identity'):replace(original, content=BadContent())})
    try: await ctx.call_block('echo.identity', {'text':'合成'})
    except PlatformError as exc: assert exc.error.stage == 'blocks.echo.identity.output'
    else: raise AssertionError()
    assert [s.status for s in app.state.runs.get(run.run_id).steps] == ['completed','failed','failed']
    print('合成块执行、非法输入/输出阶段、三次独立步骤记录通过')

asyncio.run(main())
