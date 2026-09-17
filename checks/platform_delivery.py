"""M1 合成模型闭环：真实本地 HTTP，不验证模型语义。"""
import asyncio
import json
import httpx
from local_http import local_http
from agent_platform.application import create_app
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite

async def main():
    calls = []
    async def responder(head, body, reader):
        request = json.loads(body)
        limit = request['options']['num_predict']
        calls.append(limit)
        return 200, {'done':True, 'done_reason':'stop', 'message':{'role':'assistant','content':json.dumps({'text':f'固定配置 {limit}'})},
                     'prompt_eval_count':2, 'eval_count':3}
    async with local_http(responder) as url:
        app = create_app()
        env = app.state.environments.save(EnvironmentWrite(name='闭环模型替身',connections=[{
            'connectionId':'model','kind':'model','baseUrl':url,'model':'synthetic'}]))
        app.state.packages.load('examples/execution/model-package')
        loaded = app.state.definitions.load('examples/execution/model-instance')
        definition = loaded.definition.model_dump(by_alias=True)
        definition['environmentRefs'] = [env.environment_id]
        definition['capabilityBindings'][0]['environmentId'] = env.environment_id
        definition['budget']['strictTokenLimit'] = False
        definition['configRefs'][0]['values']['maxOutputTokens'] = 10
        body = {'name':'平台闭环','definitionLoadId':loaded.load_id,'definition':definition}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local') as client:
            a = await client.post('/api/v1/services',json=body)
            assert a.status_code == 201, a.text
            a = a.json()
            service_id = a['serviceId']
            queued_a = (await client.post('/api/v1/runs',json={'serviceId':service_id,'input':{'text':'合成 A'}})).json()
            assert queued_a['status'] == 'queued'
            definition['configRefs'][0]['values']['maxOutputTokens'] = 20
            b = await client.post(f'/api/v1/services/{service_id}/versions',json=body)
            assert b.status_code == 201, b.text
            b = b.json()
            assert b['current']['version'] == '1.1' and b['activeInstanceId'] != a['activeInstanceId']
            queued_b = (await client.post('/api/v1/runs',json={'serviceId':service_id,'input':{'text':'合成 B'}})).json()
            occupied = await client.put(f'/api/v1/environments/{env.environment_id}',json={
                'name':'占用时修改','connections':[c.model_dump(mode='json',by_alias=True) for c in env.connections]})
            assert occupied.status_code == 409 and occupied.json()['code'] == 'ENVIRONMENT_IN_USE'
            retired = await client.post('/api/v1/runs',json={'serviceId':service_id,'expectedInstanceId':a['activeInstanceId'],'input':{'text':'旧入口'}})
            assert retired.status_code == 409
            rollback = await client.post(f'/api/v1/services/{service_id}/activate',json={'instanceId':a['activeInstanceId']})
            assert rollback.status_code == 200 and rollback.json()['current']['version'] == '1.0'
            assert (await client.get(f"/api/v1/runs/{queued_a['runId']}")).json()['instanceId'] == a['activeInstanceId']
            assert (await client.get(f"/api/v1/runs/{queued_b['runId']}")).json()['instanceId'] == b['activeInstanceId']
            async with app.router.lifespan_context(app):
                await asyncio.wait_for(app.state.submission.queue.join(),5)
                for run, expected, instance in [(queued_a,10,a),(queued_b,20,b)]:
                    detail = (await client.get('/api/v1/runs/'+run['runId'])).json()
                    result = await client.get('/api/v1/runs/'+run['runId']+'/result')
                    assert detail['status'] == 'completed', detail['error']
                    assert result.json()['result'] == {'text':f'固定配置 {expected}'}
                    assert detail['instanceId'] == instance['activeInstanceId']
                    assert detail['usage']['loops']['global'] == 1
                    assert detail['usage']['tokens']['global']['totalTokens'] == 5
                assert calls == [10,20]
                after = (await client.get(f'/api/v1/services/{service_id}/schema')).json()
                assert after['service']['activeInstanceId'] == a['activeInstanceId']
                assert not app.state.environments.get(env.environment_id).active_run_ids
                assert (await client.put(f'/api/v1/environments/{env.environment_id}',json={
                    'name':'任务结束可修改','connections':[c.model_dump(mode='json',by_alias=True) for c in env.connections]})).status_code == 200
    print('M1 PASS: 合成模型配置→更新→提交→回退→查询；排队 A/B 固定 10/20；环境占用拒绝/释放；退役拒绝；局部全局计量')

asyncio.run(main())
