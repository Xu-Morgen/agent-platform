"""新版复制模板；确定性控制流及本地协议替身，不调用真实模型。"""
import asyncio
import json
import sys
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'samples'))
from flow_templates import load_template
from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from similarity_support import execute, ollama_response
from local_http import local_http


async def main():
    calls = []
    async def respond(head, body, reader):
        calls.append(json.loads(body))
        return 200, ollama_response({'text': '第' + str(len(calls)) + '次合成结果'})
    with TemporaryDirectory() as directory:
        root = Path(directory) / 'copied'
        copytree('samples/template', root)
        manifest = root / 'packages/example/package.json'
        value = json.loads(manifest.read_text()); value['packageId'] = 'copied-package'
        manifest.write_text(json.dumps(value))
        block = root / 'blocks/text.py'; block.write_text(block.read_text().replace('template-text', 'copied-text'))
        async with local_http(respond) as url:
            app = create_app()
            env = app.state.environments.save(EnvironmentWrite(name='模板替身', connections=[{
                'connectionId':'model','kind':'model','model':'synthetic','baseUrl':url}]))
            def request(method, path, **kwargs):
                assert (method, path) == ('POST', 'catalog/load')
                return app.state.catalog.load(CatalogLoad.model_validate(kwargs['json'])).model_dump(by_alias=True, mode='json')
            app.state.worker.start()
            for name in ['sequence', 'branch', 'repeat', 'while', 'two-packages']:
                flow = load_template(request, root, name, env.environment_id, False)
                service = app.state.services.save(ServiceWrite(name=name, flow=flow))
                pending = app.state.submission.submit(RunSubmit(service_id=service.service_id, input={'text':'合成模板输入'}))
                await app.state.submission.queue.join()
                run = app.state.runs.get(pending.run_id)
                assert run.status == 'completed', run.error
                assert run.result == {'text': '第2次合成结果' if name == 'two-packages' else '合成模板输入'}
                if name == 'two-packages':
                    assert run.usage['loops'] == {'global':2,'bindings':{'first':1,'second':1}}
                    assert [c['options']['num_predict'] for c in calls] == [128,256]
                    assert calls[1]['messages'][1]['content'] == '第1次合成结果'
                    assert calls[0]['messages'][0]['content'] != calls[1]['messages'][0]['content']
                else:
                    assert run.environment_snapshot == [] and run.usage == {}
            await app.state.worker.stop()
    print('PASS I8-T06: copied IDs, pure sequence/branch/repeat/while and same-package independent configs; local model substitute')


if __name__ == '__main__':
    asyncio.run(main())
