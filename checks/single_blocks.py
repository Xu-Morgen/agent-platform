import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from pydantic import ValidationError
from agent_platform.registry.single_blocks import SingleBlockRegistry
from agent_platform.contracts.errors import PlatformError

async def main():
    registry = SingleBlockRegistry()
    rename = registry.load('examples/flows/blocks/rename.py')
    assert (await rename.invoke({'legacyText': 'hello'})).text == 'hello'
    condition = registry.load('examples/flows/blocks/condition.py')
    assert await condition.invoke({'text': ' '}) is False
    lms = registry.load('examples/flows/blocks/lms.py')
    assert (await lms.invoke({'code': '10000', 'bizData': {'text': 'hello'}})).text == 'hello'
    for value in [{'code': 'bad'}, {'code': '10000', 'bizData': {'text': 3}}]:
        try:
            await lms.invoke(value)
        except (ValidationError, PlatformError):
            pass
        else:
            raise AssertionError('LMS 错误未拒绝')
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'block.py'
        header = "from agent_platform.blocks import block\n@block(id='test', version='1.0.0', name='test')\n"
        for source in ['x=1', header + 'def f(value): return value', header + 'def f(value: str) -> str: return value\n' + header + 'def g(value: str) -> str: return value']:
            path.write_text(source)
            try:
                SingleBlockRegistry().load(path)
            except PlatformError:
                pass
            else:
                raise AssertionError('非法声明未拒绝')
        path.write_text(header + "def f(value: str) -> bool: return 'true'")
        loaded = SingleBlockRegistry().load(path)  # 返回值错误仅在调用时校验，加载不调用。
        try:
            await loaded.invoke('x')
        except (ValidationError, PlatformError):
            pass
        else:
            raise AssertionError('bool 输出接受字符串')
        path.write_text(header + 'def f(value: str) -> str: return value')
        loaded = SingleBlockRegistry().load(path)
        path.write_text('raise RuntimeError("changed")')
        assert await loaded.invoke('fixed') == 'fixed'
        assert b'return value' in loaded.content.files['block.py']
    print('single blocks: OK (3 示例、声明拒绝、严格 bool、源码快照)')

asyncio.run(main())
