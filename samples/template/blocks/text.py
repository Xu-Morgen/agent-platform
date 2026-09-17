from pydantic import Field
from agent_platform.contracts.base import StrictModel
from agent_platform.blocks import block


class Message(StrictModel):
    text: str = Field(min_length=1)


@block(id='template-text', version='1.0.0', name='文本透传', description='保持非空文本契约，用于纯块与循环样例')
def run(value: Message) -> Message:
    return value
