from pydantic import Field
from agent_platform.contracts.base import StrictModel
from agent_platform.blocks import block


class Message(StrictModel):
    text: str = Field(min_length=1)


@block(id='template-condition', version='1.0.0', name='继续条件', description='文本为 continue 时返回严格 bool 真')
def run(value: Message) -> bool:
    return value.text == 'continue'
