from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel


class Input(StrictModel):
    text: str


@block(id='has-text', version='1.0.0', name='非空条件', description='判断文本是否包含非空白内容')
def condition(value: Input) -> bool:
    return bool(value.text.strip())
