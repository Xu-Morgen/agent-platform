"""I5 局部验收共用装配；模型响应由调用方显式选择替身或真实环境。"""
import asyncio
import json
from pathlib import Path
from agent_platform.application import create_app
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit

ROOT = Path('samples/assignment-similarity')


def configure(url, instance_dir, *, model='synthetic', strict=False, timeout=30.0):
    app = create_app()
    env = app.state.environments.save(EnvironmentWrite(name='I5 验收环境', connections=[{
        'connectionId':'model', 'kind':'model', 'model':model, 'baseUrl':url,
        'timeoutSeconds':timeout}]))
    app.state.packages.load(ROOT / 'packages/semantic')
    loaded = app.state.definitions.load(instance_dir)
    definition = loaded.definition.model_dump(by_alias=True)
    definition['environmentRefs'] = [env.environment_id]
    definition['budget']['strictTokenLimit'] = strict
    for binding in definition['capabilityBindings']:
        binding['environmentId'] = env.environment_id
    service = app.state.services.save(ServiceWrite(name='I5 验收',
        definition_load_id=loaded.load_id, definition=definition))
    return app, service


async def execute(app, service, value, timeout=10):
    run = app.state.submission.submit(RunSubmit(service_id=service.service_id, input=value))
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(app.state.submission.queue.join(), timeout)
    return app.state.runs.get(run.run_id)


def qualitative(count):
    return {'items':[{'comparisonIndex':index, 'relation':'no_clear_relation',
        'reason':'本地协议替身，仅验收结构。', 'suggestion':'不作为真实模型结论。'} for index in range(count)]}


def ollama_response(output):
    return {'done':True, 'done_reason':'stop', 'message':{'role':'assistant',
        'content':json.dumps(output, ensure_ascii=False)}, 'prompt_eval_count':32, 'eval_count':16}
