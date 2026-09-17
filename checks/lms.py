from agent_platform.registry.blocks import BlockRegistry
from agent_platform.contracts.errors import PlatformError
b = BlockRegistry().load('examples/execution/lms')
model = b.content.load(b.manifest.input_model)
execute = b.content.load(b.manifest.entry)
assert execute(model(code='10000', biz_data={'text':'合成'})).text == '合成'
try: execute(model(code='20000', msg='合成失败', sub_code='X', sub_msg='合成原因', biz_data='not-an-object'))
except PlatformError as exc:
    assert exc.error.details.upstream_code == '20000' and exc.error.details.upstream_sub_msg == '合成原因'
else: raise AssertionError()
try: execute(model(code='10000', biz_data='not-an-object'))
except PlatformError as exc: assert exc.error.code == 'OUTPUT_VALIDATION_ERROR'
else: raise AssertionError()
print('LMS：成功提取对象，失败保留四个外壳字段，bizData 类型错误拒绝')
