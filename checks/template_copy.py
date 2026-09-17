import asyncio
import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from agent_platform.application import create_app
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from similarity_support import execute, ollama_response
from local_http import local_http


async def main():
    calls = []
    async def respond(head, body, reader):
        calls.append(json.loads(body))
        return 200, ollama_response({'text': '第' + str(len(calls)) + '次合成结果'})
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for name in ('alpha', 'beta'):
            copytree('samples/template/packages/example', root / name)
            path = root / name / 'package.json'
            manifest = json.loads(path.read_text()); manifest['packageId'] = name
            path.write_text(json.dumps(manifest))
        copytree('samples/template/instance', root / 'pipeline')
        path = root / 'pipeline/instance.json'
        definition = json.loads(path.read_text()); definition['definitionId'] = 'copied-pipeline'
        for index, name in enumerate(('alpha','beta')):
            definition['packageBindings'][index]['packageId'] = name
            definition['configRefs'][index]['configId'] = name + '-config'
            definition['configRefs'][index]['values']['maxOutputTokens'] = [11,17][index]
        path.write_text(json.dumps(definition))
        async with local_http(respond) as url:
            app = create_app()
            environment = app.state.environments.save(EnvironmentWrite(name='复制模板验收', connections=[{
                'connectionId':'model','kind':'model','model':'synthetic','baseUrl':url}]))
            for name in ('alpha','beta'): app.state.packages.load(root/name)
            loaded = app.state.definitions.load(root/'pipeline')
            definition = loaded.definition.model_dump(by_alias=True)
            definition['budget']['strictTokenLimit'] = False
            definition['environmentRefs'] = [environment.environment_id]
            for binding in definition['capabilityBindings']: binding['environmentId'] = environment.environment_id
            service = app.state.services.save(ServiceWrite(name='复制组合',definition_load_id=loaded.load_id,definition=definition))
            run = await execute(app, service, {'text':'合成模板输入'})
            assert run.status == 'completed', run.error
            assert run.result == {'text':'第2次合成结果'}
            assert run.usage['loops'] == {'global':2,'bindings':{'first':1,'second':1}}
            assert [call['options']['num_predict'] for call in calls] == [11,17]
            assert calls[1]['messages'][1]['content'] == '第1次合成结果'
            assert calls[0]['messages'][0]['content'] != calls[1]['messages'][0]['content']
    print('I5-T06：复制并重命名两个包与实例，两配置独立生效、顺序传递输出、global loop=2；平台源码无改动')


if __name__ == '__main__':
    asyncio.run(main())
