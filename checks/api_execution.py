import asyncio
from dataclasses import replace
from services import setup_app
from local_http import local_http
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.instances import CapabilityBinding
from agent_platform.contracts.errors import PlatformError
from agent_platform.runtime.context import RunContext
from agent_platform.adapters.api import APIAdapter
from agent_platform.blocks.lms import unwrap

async def main():
    mode = 'success'
    calls = []
    async def respond(head, body, reader):
        calls.append(head.split(b'\r\n')[0])
        if mode == 'timeout': await reader.read()  # 等客户端关闭，避免 sleep
        if mode == 'invalid': return 200, {'wrong':True}
        return 200, {'code':'10000' if mode == 'success' else '20000', 'bizData':{'text':'合成'}}
    async with local_http(respond) as url:
        app, body = setup_app()
        loaded = app.state.blocks.load('examples/execution/lms')
        env = app.state.environments.save(EnvironmentWrite(name='本地替身', connections=[{'connectionId':'api','kind':'api','baseUrl':url,'timeoutSeconds':0.1}]))
        body['definition']['environmentRefs'] = [env.environment_id]
        svc = app.state.services.save(ServiceWrite.model_validate(body))
        run = app.state.submission.submit(RunSubmit(service_id=svc.service_id,input={'text':'输入'}))
        snap = app.state.services.resolve_current(svc.service_id)
        definition = snap.definition
        definition.capability_bindings.append(CapabilityBinding(package_binding_id='echo', capability_id='remote', kind='api',
            environment_id=env.environment_id, connection_id='api', api_method='POST', api_path='/data', input_model='models:Message', output_model='models:Message'))
        # 仅替换本检查的输出符号为真实 LMS 外壳契约，生产声明仍经组合校验。
        class Content:
            def load(self, ref):
                from agent_platform.blocks.lms import LMSResponse
                return LMSResponse if ref == 'models:Envelope' else snap.content.load(ref)
        definition.capability_bindings[-1].output_model = 'models:Envelope'
        adapter = APIAdapter(app.state.credentials)
        ctx = RunContext(run.run_id, replace(snap, definition_json=definition.model_dump_json(), content=Content()), app.state.runs, adapter)
        output_model = loaded.content.load('block:Message')
        result = await ctx.call_api('echo.remote', {'text':'合成'})
        assert unwrap(result, output_model).text == '合成'
        mode = 'failure'
        try: unwrap(await ctx.call_api('echo.remote', {'text':'合成'}), output_model)
        except PlatformError as exc: assert exc.error.code == 'UPSTREAM_BUSINESS_ERROR'
        else: raise AssertionError()
        for mode, code in [('invalid','OUTPUT_VALIDATION_ERROR'), ('timeout','API_TIMEOUT')]:
            try: await ctx.call_api('echo.remote', {'text':'合成'})
            except PlatformError as exc: assert exc.error.code == code
            else: raise AssertionError()
        await adapter.close()
        assert calls == [b'POST /data HTTP/1.1'] * 4
    print('本地真实 HTTP：API 成功接 LMS、业务失败、契约错误、超时；每次仅一次请求通过')

asyncio.run(main())
