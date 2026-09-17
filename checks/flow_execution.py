"""新拼图执行的局部样例；模型使用明确的合成响应。"""
import asyncio
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from pathlib import Path
from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.models import ModelResponse, ModelUsage
from agent_platform.contracts.errors import PlatformError
from agent_platform.flows.execution import compile_flow
from agent_platform.flows.context import FlowRunContext
from agent_platform.runtime.context import current_context

bind = lambda source: [{'source': source}]
ref = lambda node: {'kind': 'node', 'nodeId': node}


def fixture():
    app = create_app()
    catalog = app.state.catalog
    rename = catalog.load(CatalogLoad(kind='block', path='examples/flows/blocks/rename.py'))
    package = catalog.load(CatalogLoad(kind='package', path='examples/execution/model-package'))
    env = app.state.environments.save(EnvironmentWrite(name='synthetic', connections=[{
        'connectionId': 'model', 'kind': 'model', 'baseUrl': 'http://localhost:11434', 'model': 'synthetic'}]))
    with TemporaryDirectory() as folder:
        path = Path(folder) / 'assemble.py'
        path.write_text('''from agent_platform.blocks import block
from agent_platform.contracts import StrictModel
class Pair(StrictModel):
    original: str
    generated: str
@block(id="assemble", version="1.0.0", name="组装")
def assemble(value: Pair) -> Pair:
    return value
''')
        assembly = catalog.load(CatalogLoad(kind='block', path=str(path)))
    draft = FlowDraft.model_validate({'name': '顺序执行', 'inputContract': rename.input_contract,
        'outputContract': assembly.output_contract, 'flow': [
            {'nodeId': 'convert', 'kind': 'block', 'artifactRef': rename.resource_id, 'inputs': bind({'kind': 'input'})},
            {'nodeId': 'generate', 'kind': 'package', 'artifactRef': package.resource_id, 'inputs': bind(ref('convert'))},
            {'nodeId': 'assemble', 'kind': 'block', 'artifactRef': assembly.resource_id, 'inputs': [
                {'target': ['original'], 'source': {**ref('convert'), 'path': ['text']}},
                {'target': ['generated'], 'source': {**ref('generate'), 'path': ['text']}}]}],
        'output': bind(ref('assemble')), 'budget': {'loopLimit': 10, 'tokenLimit': 10000, 'strictTokenLimit': False},
        'nodeConfigurations': {'generate': {'parameters': {'maxOutputTokens': 64},
            'budget': {'loopLimit': 10, 'tokenLimit': 10000}, 'capabilities': {'chat': {
                'kind': 'model', 'environmentId': env.environment_id, 'connectionId': 'model'}}}}})
    return app, draft, env


class SyntheticModel:
    calls = 0
    async def invoke(self, connection, request):
        self.calls += 1
        return ModelResponse(output={'text': '合成输出'}, usage=ModelUsage(input_tokens=1, output_tokens=1, quality='exact', source='synthetic'))


def context(app, draft, env, model=None):
    packages = {n.node_id: app.state.catalog.artifact(n.artifact_ref) for n in draft.flow if n.kind == 'package'}
    snapshot = SimpleNamespace(draft=draft, catalog=app.state.catalog, packages=packages, definition=draft,
        configuration={'packages.' + key: {**c.parameters, **c.budget.model_dump(by_alias=True)} for key, c in draft.node_configurations.items()})
    run = app.state.runs.create(service_id='s', instance_id='i', version='1.0', revision=1,
        input={}, environment_snapshot=[env])
    return FlowRunContext(run.run_id, snapshot, app.state.runs, model=model or SyntheticModel())


async def main():
    app, draft, env = fixture()
    executor = compile_flow(draft, app.state.catalog)
    ctx = context(app, draft, env)
    token = current_context.set(ctx)
    try:
        first = await executor.run({'legacyText': '原文'})
        assert first == {'original': '原文', 'generated': '合成输出'}
        first['original'] = '污染'
        assert (await executor.run({'legacyText': '第二次'}))['original'] == '第二次'
        try:
            await executor.run({'legacyText': 1})
        except PlatformError as exc:
            assert exc.error.code == 'CONTRACT_VALIDATION_ERROR'
        else: raise AssertionError('错误输入被接受')
        class BadModel(SyntheticModel):
            async def invoke(self, connection, request):
                return ModelResponse(output={'text': 1}, usage=ModelUsage(input_tokens=1, output_tokens=1, quality='exact', source='synthetic'))
        ctx.model = BadModel()
        try: await executor.run({'legacyText': '错误输出'})
        except PlatformError as exc:
            assert exc.error.code == 'OUTPUT_VALIDATION_ERROR' and exc.error.node_id == 'generate'
        else: raise AssertionError('错误输出被接受')
    finally: current_context.reset(token)
    print('flow execution: OK (块→包→多源组装、输入/输出校验、任务值隔离；合成模型)')

if __name__ == '__main__': asyncio.run(main())
