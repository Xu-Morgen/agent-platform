import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
from configuration import setup
from agent_platform.registry.snapshots import capture
from agent_platform.versions.snapshots import SnapshotRepository
from agent_platform.contracts.errors import PlatformError

args = list(setup())
repo = SnapshotRepository()
with TemporaryDirectory() as directory:
    shutil.copytree('examples/configuration/instance', directory, dirs_exist_ok=True)
    args[1] = capture(directory)
    saved = repo.save(*args)
    original = saved.content.read_resource('entry.py')
    Path(directory, 'entry.py').write_text('broken source')
    args[0]['configRefs'][0]['values']['loopLimit'] = 99
    assert saved.definition.config_refs[0].values['loopLimit'] == 2
    assert saved.content.read_resource('entry.py') == original
    saved.definition.config_refs[0].values['loopLimit'] = 999
    saved.configuration['packages.echo']['loopLimit'] = 999
    assert saved.configuration['packages.echo']['loopLimit'] == 2
    assert asyncio.run(saved.graph.run({'text':'synthetic'})).text == 'synthetic'
    args[0]['entry'] = 'missing:run'
    try: repo.save(*args)
    except PlatformError: pass
    else: raise AssertionError('incomplete saved')
    assert len(repo._items) == 1
print('I2-T06 PASS: immutable sources/configuration/contracts/packages/blocks, graph compiled, incomplete rejected')
