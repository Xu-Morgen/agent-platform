from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
from agent_platform.registry.blocks import BlockRegistry
from agent_platform.contracts.errors import PlatformError

registry = BlockRegistry()
artifact = registry.load('examples/configuration/block')
assert registry.get('identity', '1.0.0') is artifact
assert artifact.content.load(artifact.manifest.input_model).model_json_schema()['required'] == ['text']
with TemporaryDirectory() as directory:
    shutil.copytree('examples/configuration/block', directory, dirs_exist_ok=True)
    Path(directory, 'block.py').write_text('')
    try:
        registry.load(directory)
    except PlatformError as exc:
        assert exc.error.field_path == ['entry']
    else:
        raise AssertionError('missing entry accepted')
print('I2-T04 PASS: local block registered with contracts; missing entry rejected')
