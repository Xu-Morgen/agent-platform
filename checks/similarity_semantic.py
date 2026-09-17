import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from local_http import local_http
from similarity_support import ROOT, configure, execute, qualitative, ollama_response


def standalone(directory):
    """仅驱动语义包的测试实例，不含清洗或定量业务。"""
    path = Path(directory)
    definition = json.loads(Path('examples/execution/model-instance/instance.json').read_text())
    definition.update(definitionId='semantic-check', inputModel='models:SimilarityInput', outputModel='models:QualitativeReport')
    definition['packageBindings'][0]['packageId'] = 'text-semantic'
    definition['configRefs'][0]['values'] = {'loopLimit':1, 'tokenLimit':32768, 'maxOutputTokens':4096}
    (path / 'instance.json').write_text(json.dumps(definition))
    (path / 'models.py').write_text((ROOT / 'instance/contracts.py').read_text() +
        '\nfrom agent_platform.contracts.models import ModelRequest, ModelResponse\n')
    (path / 'entry.py').write_text("async def run(value, context):\n    return await context.invoke_package('assistant', value)\n")
    (path / 'workflow.py').write_text("from agent_platform.runtime.graphs import build_sequential\nfrom .models import SimilarityInput\ndef build_graph():\n    return build_sequential(SimilarityInput, [('identity', lambda state: {})])\n")
    return path


async def main():
    valid = qualitative(2)
    duplicate = deepcopy(valid); duplicate['items'][1]['comparisonIndex'] = 0
    wrong = deepcopy(valid); wrong['items'][0]['reason'] = 2
    extra = deepcopy(valid); extra['isPlagiarism'] = False
    for output, success in [(valid, True), ({}, False), ({'items':valid['items'][:1]}, False),
                            (duplicate, False), (wrong, False), (extra, False)]:
        calls = []
        async def respond(head, body, reader):
            calls.append(json.loads(body))
            return 200, ollama_response(output)
        with TemporaryDirectory() as directory:
            async with local_http(respond) as url:
                app, service = configure(url, standalone(directory))
                result = await execute(app, service, {'targetText':'甲乙', 'comparisonTexts':['甲乙','其他']})
                assert result.status == ('completed' if success else 'failed'), result.error
                assert len(calls) == 1
                assert result.usage['loops']['global'] == 1
                assert result.result == (valid if success else None)
                if not success:
                    assert result.error.code == 'OUTPUT_VALIDATION_ERROR'
                assert len([step for step in result.steps if step.kind == 'package']) == 1
                assert calls[0]['options']['num_predict'] == 4096
    print('I5-T04：真实适配器→本地 HTTP 协议替身，合法输出、缺项/重复/类型错误拒绝；每次尝试 loop=1')


if __name__ == '__main__':
    asyncio.run(main())
