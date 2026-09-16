import json
from copy import deepcopy
from pathlib import Path
from pydantic import ValidationError
from agent_platform.contracts import export_schema
from agent_platform.contracts.packages import PackageManifest, PackageBudget, InstanceBudget

sample = json.loads(Path('examples/declarations/package.json').read_text())
assert PackageManifest.model_validate(sample).entry == 'entry:invoke'
invalid = deepcopy(sample)
del invalid['entry']
for data, path in [(invalid, ('entry',))] + [
    ({**sample, 'budgetDefaults': {'loopLimit': value, 'tokenLimit': 100}}, ('budgetDefaults', 'loopLimit'))
    for value in (0, -1, '1', True)
] + [({**sample, 'budgetDefaults': {'loopLimit': 1, 'tokenLimit': 0}}, ('budgetDefaults', 'tokenLimit'))]:
    try:
        PackageManifest.model_validate(data)
    except ValidationError as e:
        assert e.errors()[0]['loc'] == path
    else:
        raise AssertionError(data)
assert export_schema(PackageBudget)['properties']['loopLimit']['exclusiveMinimum'] == 0
assert InstanceBudget().strict_token_limit is True
print('T10 PASS: package declaration, missing entry and invalid budgets with field paths')
