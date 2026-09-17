import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.errors import PlatformError
from agent_platform.flows.execution import compile_flow
from agent_platform.flows.validation import validate_flow
from flow_execution import bind, ref

async def main():
    catalog = create_app().state.catalog
    with TemporaryDirectory() as folder:
        modules = {}
        for name, output, expression in [('increment', 'int', 'value + 1'), ('condition', 'bool', 'value < 3')]:
            p = Path(folder) / (name + '.py')
            p.write_text(f'from agent_platform.blocks import block\n@block(id="{name}", version="1.0.0", name="{name}")\ndef run(value: int) -> {output}:\n    return {expression}\n')
            modules[name] = catalog.load(CatalogLoad(kind='block', path=str(p)))
    inc, cond = modules['increment'], modules['condition']
    carry = {'kind': 'carry', 'nodeId': 'loop'}
    loop = {'nodeId': 'loop', 'kind': 'repeat', 'count': 3,
        'carry': {'contract': inc.input_contract, 'initial': bind({'kind': 'input'}), 'update': bind(ref('inc'))},
        'body': [{'nodeId': 'inc', 'kind': 'block', 'artifactRef': inc.resource_id, 'inputs': bind(carry)}]}
    doc = {'name': '循环', 'inputContract': inc.input_contract, 'outputContract': inc.output_contract,
           'flow': [loop], 'output': bind(ref('loop'))}
    async def run(value): return await compile_flow(FlowDraft.model_validate(doc), catalog).run(value)
    assert await run(0) == 3
    loop['count'] = 0
    assert await run(9) == 9
    del loop['count']; loop.update(kind='while', maxIterations=3,
        condition={'nodeId': 'test', 'kind': 'block', 'artifactRef': cond.resource_id, 'inputs': bind(carry)})
    assert await run(0) == 3 and await run(8) == 8
    loop['maxIterations'] = 2
    try: await run(0)
    except PlatformError as exc: assert exc.error.code == 'LOOP_ITERATION_LIMIT'
    else: raise AssertionError('循环上限未拦截')
    loop['maxIterations'] = 3
    # 循环内 if，再嵌套 repeat；每轮从本轮携带值开始。
    loop['body'] = [
        {'nodeId': 'innerTest', 'kind': 'block', 'artifactRef': cond.resource_id, 'inputs': bind(carry)},
        {'nodeId': 'branch', 'kind': 'if', 'condition': ref('innerTest'), 'outputContract': inc.output_contract,
         'thenBranch': {'nodes': [{'nodeId': 'inner', 'kind': 'repeat', 'count': 1,
             'carry': {'contract': inc.input_contract, 'initial': bind(carry), 'update': bind(ref('inc'))},
             'body': [{'nodeId': 'inc', 'kind': 'block', 'artifactRef': inc.resource_id,
                       'inputs': bind({'kind': 'carry', 'nodeId': 'inner'})}]}], 'output': bind(ref('inner'))},
         'elseBranch': {'nodes': [], 'output': bind(carry)}}]
    loop['carry']['update'] = bind(ref('branch'))
    assert await run(0) == 3
    doc['output'] = bind(ref('inc'))
    assert not validate_flow(FlowDraft.model_validate(doc), catalog).valid
    loop['carry']['initial'] = bind(ref('branch'))
    assert not validate_flow(FlowDraft.model_validate(doc), catalog).valid
    print('flow loops: OK (repeat/while、零次初值、上限错误、嵌套循环与条件、作用域反馈拒绝)')

asyncio.run(main())
