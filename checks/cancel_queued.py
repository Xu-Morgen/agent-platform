import asyncio
import httpx
from services import setup_app
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.runtime.boundary import Boundary
from agent_platform.runtime.worker import RunWorker

async def main():
    app, body = setup_app()
    env = app.state.environments.save(EnvironmentWrite(name='合成', connections=[{'connectionId':'api','kind':'api','baseUrl':'http://localhost:9000'}]))
    body['definition']['environmentRefs'] = [env.environment_id]
    svc = app.state.services.save(ServiceWrite.model_validate(body))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for race in (False, True):
            run = app.state.submission.submit(RunSubmit(service_id=svc.service_id, input={'text':'合成'}))
            reached, release = asyncio.Event(), asyncio.Event()
            async def observer(phase, step):
                if phase == 'run_start':
                    reached.set()
                    await release.wait()
            worker = RunWorker(app.state.submission, lambda: Boundary(observer=observer))
            if race:
                worker.start()
                await asyncio.wait_for(reached.wait(), 2)
            result = await client.post(f'/api/v1/runs/{run.run_id}/cancel')
            assert result.status_code == 200 and result.json()['status'] == 'cancelled'
            assert not app.state.environments.get(env.environment_id).active_run_ids
            assert (await client.post(f'/api/v1/runs/{run.run_id}/cancel')).json() == result.json()
            release.set()
            if not race:
                worker.start()
            await asyncio.wait_for(app.state.submission.queue.join(), 2)
            await worker.stop()
            assert app.state.runs.get(run.run_id).steps == []
        assert (await client.post('/api/v1/runs/missing/cancel')).status_code == 404
    print('PASS: 暂停 worker 取消后不执行；事件屏障调度竞争；环境释放；终态幂等；404')

asyncio.run(main())
