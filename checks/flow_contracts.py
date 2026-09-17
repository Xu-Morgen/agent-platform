"""I6-T01：协议导出与结构边界。"""
import json
from copy import deepcopy
from pathlib import Path
from pydantic import ValidationError
from agent_platform.contracts.base import export_schema
from agent_platform.contracts.flows import FlowDraft

root = Path('examples/flows')
ref = lambda node: {'kind': 'node', 'nodeId': node}
bind = lambda source: [{'source': source}]
carry = {'contract': 'text', 'initial': bind({'kind': 'input'}), 'update': bind({'kind': 'carry', 'nodeId': 'repeat'})}
example = {'name': '控制结构协议', 'inputContract': 'text', 'outputContract': 'text', 'flow': [
    {'nodeId': 'condition', 'kind': 'block', 'artifactRef': 'condition', 'inputs': bind({'kind': 'input'})},
    {'nodeId': 'choose', 'kind': 'if', 'condition': ref('condition'), 'outputContract': 'text',
     'thenBranch': {'nodes': [], 'output': bind({'kind': 'input'})},
     'elseBranch': {'nodes': [], 'output': bind({'kind': 'input'})}},
    {'nodeId': 'repeat', 'kind': 'repeat', 'count': 0, 'carry': carry},
    {'nodeId': 'while', 'kind': 'while', 'maxIterations': 3,
     'condition': {'nodeId': 'check', 'kind': 'block', 'artifactRef': 'condition', 'inputs': bind({'kind': 'carry', 'nodeId': 'while'})},
     'carry': {**carry, 'update': bind({'kind': 'carry', 'nodeId': 'while'})}},
], 'output': bind(ref('while'))}
assert FlowDraft.model_validate(example).budget is None
for mutate in [lambda x: x['flow'][0].update(kind='unknown'),
               lambda x: x['flow'][1].update(nodeId='condition'),
               lambda x: x['flow'][1].pop('condition'),
               lambda x: x['flow'][3].pop('maxIterations'),
               lambda x: x['flow'][2].update(count=True)]:
    invalid = deepcopy(example)
    mutate(invalid)
    try:
        FlowDraft.model_validate(invalid)
    except ValidationError as exc:
        assert exc.errors()[0]['loc']
    else:
        raise AssertionError('无效结构未拒绝')
if __name__ == '__main__':
    root.joinpath('flow.schema.json').write_text(json.dumps(export_schema(FlowDraft), ensure_ascii=False, indent=2) + '\n')
    root.joinpath('control.json').write_text(json.dumps(example, ensure_ascii=False, indent=2) + '\n')
    print('flow contracts: OK (顺序、条件、循环与 5 个拒绝场景)')
