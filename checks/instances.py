import json
from copy import deepcopy
from pathlib import Path
from pydantic import ValidationError
from agent_platform.contracts.instances import InstanceDefinition

sample = json.loads(Path('examples/declarations/instance.json').read_text())
assert len(InstanceDefinition.model_validate(sample).package_bindings) == 1
cases = []
for key in ('packageBindings', 'configRefs'):
    cases.append(({**sample, key: []}, (key,)))
conflict = deepcopy(sample)
conflict['configRefs'].append({**conflict['configRefs'][0], 'configId': 'second'})
cases.append((conflict, ('configRefs', 1, 'values', 'loopLimit')))
missing = deepcopy(sample)
missing['configRefs'][0]['scope'] = 'packages.missing'
cases.append((missing, ('configRefs', 0, 'scope')))
for data, path in cases:
    try:
        InstanceDefinition.model_validate(data)
    except ValidationError as e:
        assert e.errors()[0]['loc'] == path, e.errors()
    else:
        raise AssertionError(data)
print('T11 PASS: one-package instance, zero bindings/configs and scoped field conflicts')
