import asyncio
from copy import deepcopy
from flow_execution import fixture, context, bind, ref
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.flows import FlowDraft
from agent_platform.flows.execution import compile_flow
from agent_platform.flows.validation import validate_flow
from agent_platform.runtime.context import current_context

async def main():
    app, draft, env = fixture()
    condition = app.state.catalog.load(CatalogLoad(kind='block', path='examples/flows/blocks/condition.py'))
    original = draft.model_dump(by_alias=True)
    package = original['flow'][1]
    original['flow'] = [original['flow'][0], {'nodeId': 'test', 'kind': 'block', 'artifactRef': condition.resource_id,
        'inputs': bind(ref('convert'))}, {'nodeId': 'choose', 'kind': 'if', 'condition': ref('test'),
        'outputContract': app.state.catalog.get(package['artifactRef']).output_contract,
        'thenBranch': {'nodes': [package], 'output': bind(ref('generate'))},
        'elseBranch': {'nodes': [], 'output': bind(ref('convert'))}}]
    original['outputContract'] = original['flow'][2]['outputContract']
    original['output'] = bind(ref('choose'))
    draft = FlowDraft.model_validate(original)
    ctx = context(app, FlowDraft.model_validate({**original, 'flow': [package]}), env)
    token = current_context.set(ctx)
    try:
        graph = compile_flow(draft, app.state.catalog)
        assert (await graph.run({'legacyText': '非空'})) == {'text': '合成输出'}
        assert (await graph.run({'legacyText': ''})) == {'text': ''}
        assert ctx.model.calls == 1
        assert len([s for s in ctx.runs.get(ctx.run_id).steps if s.kind == 'package']) == 1
        bad = deepcopy(original); bad['flow'][2]['elseBranch']['output'] = bind({'kind': 'constant', 'value': False})
        assert not validate_flow(FlowDraft.model_validate(bad), app.state.catalog).valid
        bad = deepcopy(original); bad['output'] = bind(ref('generate'))
        assert not validate_flow(FlowDraft.model_validate(bad), app.state.catalog).valid
    finally: current_context.reset(token)
    print('flow branches: OK (true/false 互斥、未选包零调用、共同出口和作用域拒绝)')

asyncio.run(main())
