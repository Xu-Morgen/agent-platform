import asyncio
import json
from local_http import local_http
from similarity_support import ROOT, configure, execute, qualitative, ollama_response


async def main():
    request = json.loads((ROOT / 'examples/input.json').read_text())
    for case in ('success', 'missing', 'transport', 'strict', 'blank-target', 'blank-comparison'):
        calls = []
        async def respond(head, body, reader):
            calls.append(json.loads(body))
            if case == 'transport':
                return 503, {'error':'synthetic failure'}
            return 200, ollama_response(qualitative(2 if case == 'success' else 1))
        async with local_http(respond) as url:
            app, service = configure(url, ROOT / 'instance', strict=(case == 'strict'))
            value = dict(request)
            if case == 'blank-target': value['targetText'] = ' \n\t'
            if case == 'blank-comparison': value['comparisonTexts'] = ['甲乙', '\t']
            run = await execute(app, service, value)
            if case == 'success':
                assert run.status == 'completed', run.error
                assert [item['similarity'] for item in run.result['quantitative']['items']] == [0.5, 0.0]
                assert run.result['qualitative'] == qualitative(2)
                assert run.usage['loops']['global'] == 1
                assert run.usage['tokens']['global']['totalTokens'] == 48
                assert [s.step_id for s in run.steps if s.kind == 'node'] == ['nodes.clean', 'nodes.quantitative', 'nodes.semantic', 'nodes.assemble']
            else:
                assert run.status == 'failed' and run.result is None
                if case == 'missing':
                    assert run.error.code == 'OUTPUT_VALIDATION_ERROR'
                    assert any(s.step_id == 'nodes.quantitative' and s.status == 'completed' for s in run.steps)
                if case.startswith('blank'):
                    assert run.error.field_path == (['targetText'] if case == 'blank-target' else ['comparisonTexts', 1])
                if case == 'strict': assert run.error.code == 'TOKEN_ACCOUNTING_UNSUPPORTED'
            assert len(calls) == (0 if case in ('strict', 'blank-target', 'blank-comparison') else 1)
            assert all(not env.active_run_ids for env in app.state.environments.list())
    print('I5-T05：四节点查重图双报告通过；语义/传输失败无部分结果；空白字段与严格不支持零请求')


if __name__ == '__main__':
    asyncio.run(main())
