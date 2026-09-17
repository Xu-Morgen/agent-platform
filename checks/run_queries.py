import asyncio
import httpx
from services import setup_app
from agent_platform.contracts.errors import ErrorResponse

async def main():
    app, body = setup_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        svc = (await c.post('/api/v1/services', json=body)).json()
        run = (await c.post('/api/v1/runs', json={'serviceId':svc['serviceId'],'input':{'text':'合成'}})).json()
        path = '/api/v1/runs/' + run['runId']
        assert (await c.get(path)).json()['status'] == 'queued'
        response = await c.get(path + '/result')
        assert response.status_code == 409 and response.json()['details']['runStatus'] == 'queued'
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(app.state.submission.queue.join(), 5)
        assert (await c.get(path + '/result')).json()['result'] == {'text':'合成'}
        bad = app.state.runs.create(service_id=svc['serviceId'], instance_id=svc['activeInstanceId'], version='1.0', revision=1, input={})
        app.state.runs.finish(bad.run_id, 'failed', error=ErrorResponse(code='MODEL_TIMEOUT',stage='model.transport',message='合成超时',run_id=bad.run_id))
        path = '/api/v1/runs/' + bad.run_id
        assert (await c.get(path)).json()['error']['code'] == 'MODEL_TIMEOUT'
        response = await c.get(path + '/result')
        assert response.status_code == 409 and response.json()['code'] == 'MODEL_TIMEOUT' and response.json()['details']['runStatus'] == 'failed'
        for suffix in ('', '/result'):
            assert (await c.get('/api/v1/runs/missing' + suffix)).status_code == 404
    print('查询：queued/409、completed 结果、failed 原因、未知 runId/404 通过')

asyncio.run(main())
