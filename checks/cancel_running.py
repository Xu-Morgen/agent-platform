import asyncio
import httpx
from dataclasses import replace
from local_http import local_http
from agent_platform.application import create_app
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit

async def case(mode='success'):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def responder(head, body, reader):
        calls.append(body)
        started.set()
        await release.wait()
        if mode == 'disconnect':
            raise ConnectionError('合成断连')
        if mode == 'timeout':
            await reader.read()
        return 200, {'done':True, 'done_reason':'stop', 'message':{'role':'assistant','content':'{"text":"合成"}'}, 'prompt_eval_count':2, 'eval_count':3}
    async with local_http(responder) as url:
        app = create_app()
        env = app.state.environments.save(EnvironmentWrite(name='取消替身', connections=[{
            'connectionId':'model','kind':'model','baseUrl':url,'model':'synthetic','timeoutSeconds':0.5 if mode == 'timeout' else 3}]))
        app.state.packages.load('examples/execution/model-package')
        loaded = app.state.definitions.load('examples/execution/model-instance')
        definition = loaded.definition.model_dump(by_alias=True)
        definition['budget']['strictTokenLimit'] = False
        definition['environmentRefs'] = [env.environment_id]
        definition['capabilityBindings'][0]['environmentId'] = env.environment_id
        svc = app.state.services.save(ServiceWrite(name='取消样例', definition_load_id=loaded.load_id, definition=definition))
        run = app.state.submission.submit(RunSubmit(service_id=svc.service_id, input={'text':'合成'}))
        pending = app.state.submission.queue.get_nowait()
        app.state.submission.queue.task_done()
        original = pending.snapshot
        later_calls = []
        class TwoCalls:
            def load(self, ref):
                if ref == original.definition.entry:
                    async def entry(value, context):
                        result = await original.content.load(ref)(value, context)
                        later_calls.append('second')
                        return await context.invoke_package('model', result)
                    return entry
                return original.content.load(ref)
        app.state.submission.queue.put_nowait(replace(pending, snapshot=replace(original, content=TwoCalls())))
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(started.wait(), 2)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post(f'/api/v1/runs/{run.run_id}/cancel')
                assert response.status_code == 200
                assert response.json()['status'] == 'running' and response.json()['cancelPhase'] == 'waiting_transport'
                assert app.state.environments.get(env.environment_id).active_run_ids == [run.run_id]
                definition['budget']['loopLimit'] += 1
                newer = app.state.services.save(ServiceWrite(name='新版本', definition_load_id=loaded.load_id, definition=definition), svc.service_id)
                release.set()
                await asyncio.wait_for(app.state.submission.queue.join(), 3)
                result = app.state.runs.get(run.run_id)
                assert result.status == ('cancelled' if mode == 'success' else 'failed') and result.cancel_requested and result.cancel_phase is None
                if mode != 'success':
                    assert result.error.code == ('MODEL_TIMEOUT' if mode == 'timeout' else 'MODEL_TRANSPORT_ERROR')
                assert result.result is None and len(calls) == 1 and later_calls == []
                assert result.usage['tokens']['global']['totalTokens'] == (5 if mode == 'success' else None)
                assert not app.state.environments.get(env.environment_id).active_run_ids
                assert (await client.post(f'/api/v1/runs/{run.run_id}/cancel')).json()['status'] == result.status
                assert app.state.services.get(svc.service_id).active_instance_id == newer.active_instance_id
                stale = await client.post('/api/v1/runs', json={'serviceId':svc.service_id,'expectedInstanceId':run.instance_id,'input':{'text':'旧实例'}})
                assert stale.status_code == 409
                env_data = app.state.environments.get(env.environment_id)
                app.state.environments.save(EnvironmentWrite(name='已解锁', connections=[c.model_dump() for c in env_data.connections]), env.environment_id)
    print(f'PASS: {mode} 取消等待终态正确，保留取消记录；后续调用 0；环境可更新；退役实例未激活')

if __name__ == '__main__':
    asyncio.run(case())
