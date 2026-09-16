from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
from agent_platform.registry import capture

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'entry.py').write_text('from .helper import value\ndef invoke(context):\n    from .late import suffix\n    return value + suffix, context.read_resource("prompt.txt").decode()\n')
    (root / 'helper.py').write_text('value = "A"\n')
    (root / 'late.py').write_text('suffix = "-old"\n')
    (root / 'prompt.txt').write_text('原始 Prompt')
    a = capture(root)
    invoke_a = a.load('entry:invoke')
    (root / 'helper.py').write_text('value = "B"\n')
    (root / 'late.py').write_text('suffix = "-new"\n')
    (root / 'prompt.txt').write_text('新的 Prompt')
    b = capture(root)
    invoke_b = b.load('entry:invoke')
    same = capture(root)
    assert same.digest == b.digest and same.namespace != b.namespace
    shutil.rmtree(root)
    assert invoke_a(a) == ('A-old', '原始 Prompt')
    assert invoke_b(b) == ('B-new', '新的 Prompt')
    assert a.digest != b.digest
    assert invoke_a.__module__ != invoke_b.__module__
    try:
        a.files['prompt.txt'] = b'mutated'
    except TypeError:
        pass
    else:
        raise AssertionError('snapshot must be immutable')
    try:
        a.read_resource('../prompt.txt')
    except ValueError:
        pass
    else:
        raise AssertionError('resource path must stay inside snapshot')
    a.close(); b.close(); same.close()
print('T12 PASS: A/B isolated code, deferred imports and prompts survive source deletion')
