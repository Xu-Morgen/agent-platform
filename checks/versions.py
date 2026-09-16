from dataclasses import replace
from types import MappingProxyType
from configuration import setup
from agent_platform.versions.snapshots import prepare_snapshot
from agent_platform.versions.numbering import VersionAllocator

args = setup()
a = prepare_snapshot(*args)
value = a.definition
value.config_refs[0].values['loopLimit'] = 3
b = prepare_snapshot(value, *args[1:])
# 合成源码变更替身，分类器仅检查内容；完整加载已由快照卡验证。
files = dict(a.content.files)
files['entry.py'] += b'\n# changed\n'
c = replace(a, content=replace(a.content, files=MappingProxyType(files)))
d = replace(b, content=c.content)
allocator = VersionAllocator()
assert allocator.allocate('service', None, a).version == '1.0'
assert allocator.allocate('service', a, b).version == '1.1'
number = allocator.allocate('service', b, replace(c, definition_json=b.definition_json, configuration_json=b.configuration_json))
assert number.version == '2.0' and number.change_kind == 'major'
number = allocator.allocate('service', a, d)
assert number.version == '3.0' and number.change_kind == 'breaking'
number = allocator.allocate('service', a, b)  # 回退 A 后再保存，仍延续分配序列。
assert number.version == '3.1' and number.revision == 5
print('I2-T07 PASS: initial/minor/major/breaking and monotonic allocation after rollback')
