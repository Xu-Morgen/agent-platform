import asyncio
import httpx
from services import setup_app
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.errors import PlatformError
from agent_platform.runtime.context import current_context
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.runtime.boundary import Boundary

async def main():
    app, body = setup_app()
    env_write = EnvironmentWrite(name='占用样例', connections=[{'connectionId':'api','kind':'api','baseUrl':'http://localhost'}])
    env = app.state.environments.save(env_write)
    body['definition']['environmentRefs'] = [env.environment_id]
    service = app.state.services.save(ServiceWrite.model_validate(body))
    a = app.state.services.resolve_current(service.service_id)
    # 先受理并关闭提交 HTTP 客户端，再切换当前版本，最后放行 worker。
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        first = (await c.post('/api/v1/runs', json={'serviceId':service.service_id,'input':{'text':'A'}})).json()
    body['definition']['configRefs'][0]['values']['loopLimit'] = 3
    b = app.state.services.save(ServiceWrite.model_validate(body), service.service_id)
    assert b.active_instance_id != a.instance_id
    pending = app.state.submission.queue._queue[0]
    assert pending.snapshot is a
    bad = app.state.submission.submit(RunSubmit(service_id=service.service_id,input={'text':'失败'}))
    good = app.state.submission.submit(RunSubmit(service_id=service.service_id,input={'text':'继续'}))
    started, resume = asyncio.Event(), asyncio.Event()
    async def policy(phase, step):
        run_id = current_context.get().run_id
        if phase == 'node_start' and run_id == first['runId']:
            started.set()
            await resume.wait()
        if phase == 'node_start' and run_id == bad.run_id:
            raise ValueError('合成节点失败')
        if phase == 'run_start' and run_id == good.run_id:
            assert bad.run_id not in app.state.environments.get(env.environment_id).active_run_ids
    app.state.worker.boundary_factory = lambda: Boundary([policy])
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), 5)
        assert app.state.runs.get(first['runId']).status == 'running'
        try:
            app.state.environments.save(env_write, env.environment_id)
        except PlatformError as exc:
            assert exc.error.code == 'ENVIRONMENT_IN_USE'
        else:
            raise AssertionError('运行中环境更新未被拒绝')
        resume.set()
        await asyncio.wait_for(app.state.submission.queue.join(), 5)
    assert app.state.runs.get(first['runId']).instance_id == a.instance_id
    assert app.state.runs.get(first['runId']).result == {'text':'A'}
    assert app.state.runs.get(bad.run_id).status == 'failed'
    assert app.state.runs.get(good.run_id).status == 'completed'
    assert not app.state.environments.get(env.environment_id).active_run_ids
    assert app.state.environments.save(env_write, env.environment_id).revision == 2
    print('HTTP 断开后执行 A 快照；失败后继续下一任务；worker 生命周期通过')

asyncio.run(main())
