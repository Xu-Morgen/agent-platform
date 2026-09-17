import asyncio
import json
from local_http import local_http
from agent_platform.application import create_app
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit

async def main():
    async def responder(head, body, reader):
        assert json.loads(body)['options']['num_predict'] == 128
        return 200, {'done':True,'done_reason':'stop','message':{'role':'assistant','content':'{"text":"本地协议替身"}'},'prompt_eval_count':12,'eval_count':8}
    async with local_http(responder) as url:
        app = create_app()
        env = app.state.environments.save(EnvironmentWrite(name='本地模型替身',connections=[{'connectionId':'model','kind':'model','model':'synthetic','baseUrl':url}]))
        app.state.packages.load('examples/execution/model-package')
        loaded = app.state.definitions.load('examples/execution/model-instance')
        definition = loaded.definition.model_dump(by_alias=True)
        definition['environmentRefs'] = [env.environment_id]
        definition['capabilityBindings'][0]['environmentId'] = env.environment_id
        svc = app.state.services.save(ServiceWrite(name='模型样例', definition_load_id=loaded.load_id, definition=definition))
        run = app.state.submission.submit(RunSubmit(service_id=svc.service_id,input={'text':'合成输入'}))
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(app.state.submission.queue.join(), 5)
        result = app.state.runs.get(run.run_id)
        assert result.status == 'completed', result.error
        assert result.result == {'text':'本地协议替身'}
        model_steps = [s for s in result.steps if s.kind == 'model']
        assert len(model_steps) == 1 and model_steps[0].usage['inputTokens'] == 12
        assert not app.state.environments.get(env.environment_id).active_run_ids
    print('固定图→包→平台模型→本地 HTTP→契约结果完整链路通过；步骤 usage 保留，环境释放')

asyncio.run(main())
