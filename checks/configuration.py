from copy import deepcopy
import json
from pathlib import Path
from agent_platform.registry.packages import PackageRegistry
from agent_platform.registry.blocks import BlockRegistry
from agent_platform.registry.snapshots import capture
from agent_platform.repositories.credentials import CredentialRepository
from agent_platform.repositories.environments import EnvironmentRepository
from agent_platform.configuration import validate_combination
from agent_platform.contracts.errors import PlatformError

def setup():
    packages, blocks = PackageRegistry(), BlockRegistry()
    for name in ('package', 'second'):
        packages.load('examples/configuration/' + name)
    blocks.load('examples/configuration/block')
    content = capture('examples/configuration/instance')
    definition = json.loads(content.read_resource('instance.json'))
    return definition, content, packages, blocks, EnvironmentRepository(CredentialRepository())

if __name__ == '__main__':
    args = setup()
    definition, packages, blocks, scopes, defaults = validate_combination(*args)
    assert definition.budget.loop_limit == 4 and definition.budget.token_limit == 200
    assert len(packages) == 2 and len(scopes) == 2
    for kind in ('dependency', 'scope', 'config'):
        value = deepcopy(args[0])
        if kind == 'dependency': value['packageBindings'][0]['version'] = '9.0.0'
        elif kind == 'scope': value['configRefs'].append({**value['configRefs'][0], 'configId': 'conflict'})
        else: value['configRefs'][0]['values']['loopLimit'] = '2'
        try: validate_combination(value, *args[1:])
        except PlatformError as exc: assert exc.error.field_path
        else: raise AssertionError(kind)
    print('I2-T05 PASS: two packages/configs, explicit summed budgets, missing dependency/scope/type errors')
