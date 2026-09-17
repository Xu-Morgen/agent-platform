import asyncio
import httpx
from services import setup_app
from agent_platform.contracts.environments import EnvironmentWrite

async def main():
    app, body = setup_app()
    env = app.state.environments.save(EnvironmentWrite(name='合成环境', connections=[{'connectionId':'api','kind':'api','baseUrl':'http://localhost'}]))
    body['definition']['environmentRefs'] = [env.environment_id]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        service = (await c.post('/api/v1/services', json=body)).json()
        request = {'serviceId':service['serviceId'], 'input':{'text':'合成'}}
        a, b = [(await c.post('/api/v1/runs', json=request)).json() for _ in range(2)]
        assert a['runId'] != b['runId'] and a['status'] == b['status'] == 'queued'
        assert (await c.post('/api/v1/runs', json={**request, 'input':{'text':1}})).status_code == 422
        assert (await c.post('/api/v1/runs', json={**request, 'expectedInstanceId':'wrong'})).status_code == 409
        assert app.state.submission.queue.qsize() == len(app.state.runs._items) == 2
        assert app.state.environments.get(env.environment_id).active_run_ids == [a['runId'], b['runId']]
    print('提交：独立 runId、422/409 不创建记录、排队占用环境通过')

if __name__ == '__main__': asyncio.run(main())
