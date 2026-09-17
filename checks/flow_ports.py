from copy import deepcopy
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.registry.catalog import ModuleCatalog
from agent_platform.registry.packages import PackageRegistry
from agent_platform.flows.compatibility import assignable, Incompatible
from agent_platform.flows.validation import validate_flow

bind = lambda source: [{'source': source}]
ref = lambda node: {'kind': 'node', 'nodeId': node}

def fixture():
    catalog = ModuleCatalog(PackageRegistry())
    rename = catalog.load(CatalogLoad(kind='block', path='examples/flows/blocks/rename.py'))
    condition = catalog.load(CatalogLoad(kind='block', path='examples/flows/blocks/condition.py'))
    draft = {'name': '端口示例', 'inputContract': rename.input_contract, 'outputContract': rename.output_contract,
        'flow': [{'nodeId': 'convert', 'kind': 'block', 'artifactRef': rename.resource_id, 'inputs': bind({'kind': 'input'})},
                 {'nodeId': 'test', 'kind': 'block', 'artifactRef': condition.resource_id, 'inputs': bind(ref('convert'))},
                 {'nodeId': 'choose', 'kind': 'if', 'condition': ref('test'), 'outputContract': rename.output_contract,
                  'thenBranch': {'nodes': [], 'output': bind(ref('convert'))}, 'elseBranch': {'nodes': [], 'output': bind(ref('convert'))}},
                 {'nodeId': 'repeat', 'kind': 'repeat', 'count': 0, 'body': [], 'carry': {'contract': rename.output_contract,
                  'initial': bind(ref('choose')), 'update': bind({'kind': 'carry', 'nodeId': 'repeat'})}}],
        'output': bind(ref('repeat'))}
    return catalog, draft

if __name__ == '__main__':
    catalog, draft = fixture()
    result = validate_flow(FlowDraft.model_validate(draft), catalog)
    assert result.valid, result
    for change in [
        lambda d: d['flow'][0].update(inputs=bind(ref('test'))),
        lambda d: d['flow'][1].update(inputs=bind({'kind': 'input'})),
        lambda d: d['flow'][2]['elseBranch'].update(output=[]),
        lambda d: d.update(output=bind({'kind': 'carry', 'nodeId': 'repeat'})),
        lambda d: d['flow'][2]['thenBranch']['nodes'].append({'nodeId': 'hidden', 'kind': 'block', 'artifactRef': catalog.list()[0].resource_id}),
    ]:
        value = deepcopy(draft); change(value)
        assert not validate_flow(FlowDraft.model_validate(value), catalog).valid
    # 分支内部节点不能跨分支或在外部读取。
    value = deepcopy(draft)
    value['flow'][2]['thenBranch']['nodes'] = [dict(value['flow'][1], nodeId='hidden')]
    value['output'] = bind(ref('hidden'))
    assert not validate_flow(FlowDraft.model_validate(value), catalog).valid
    for source, target in [
        ({'type': 'string'}, {'type': 'integer'}),
        ({'anyOf': [{'type': 'null'}, {'type': 'string'}]}, {'type': 'string'}),
        ({'type': 'integer', 'minimum': 0}, {'type': 'integer', 'minimum': 1}),
        ({'type': 'object', 'properties': {'extra': {'type': 'string'}}, 'additionalProperties': False}, {'type': 'object', 'additionalProperties': False}),
        ({'type': 'object', 'properties': {}}, {'type': 'object', 'required': ['text']}),
    ]:
        try: assignable(source, target)
        except Incompatible: pass
        else: raise AssertionError('不兼容连接被接受')
    assert any(i.source_node_id for i in validate_flow(FlowDraft.model_validate(value), catalog).issues)
    print('flow ports: OK (转换、共同出口、循环反馈、类型/范围/可空/额外字段与作用域拒绝)')
