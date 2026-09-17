"""新版查重拼图：评分边界与失败不得发布部分报告。"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'samples'))
from flow_templates import load_template
from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from local_http import local_http
from similarity_support import qualitative, ollama_response


async def main():
    mode = 'success'
    async def respond(head, body, reader):
        return 200, ollama_response(qualitative(3) if mode == 'success' else {'items': []})
    async with local_http(respond) as url:
        app = create_app()
        environment = app.state.environments.save(EnvironmentWrite(name='查重替身', connections=[{
            'connectionId':'model','kind':'model','model':'synthetic','baseUrl':url}]))
        def request(method, path, **kwargs):
            return app.state.catalog.load(CatalogLoad.model_validate(kwargs['json'])).model_dump(mode='json',by_alias=True)
        flow = load_template(request, 'samples/assignment-similarity', 'similarity', environment.environment_id, False)
        service = app.state.services.save(ServiceWrite(name='查重新版',flow=flow))
        async with app.router.lifespan_context(app):
            for mode in ['success', 'bad']:
                pending = app.state.submission.submit(RunSubmit(service_id=service.service_id, input={
                    'targetText':'甲乙\r\n丙丁', 'comparisonTexts':['其他','甲乙\n甲乙','甲乙\n丙丁']}))
                await app.state.submission.queue.join()
                run = app.state.runs.get(pending.run_id)
                if mode == 'success':
                    assert run.status == 'completed', run.error
                    assert [item['similarity'] for item in run.result['quantitative']['items']] == [0, .5, 1]
                    assert len(run.result['qualitative']['items']) == 3
                    assert 'isPlagiarism' not in run.result
                    assert run.usage['loops'] == {'global':1,'bindings':{'semantic':1}}
                else:
                    assert run.status == 'failed' and run.result is None
                    assert any('score' in s.step_id and s.status == 'completed' for s in run.steps)
                    assert any('semantic' in s.step_id and s.status == 'failed' for s in run.steps)
        print('PASS I8-T07: FlowDraft, 0/0.5/1 unchanged, both reports, earlier output assembly, failed semantic has no partial success; local substitute')


if __name__ == '__main__':
    asyncio.run(main())
