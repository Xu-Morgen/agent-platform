from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel


class Input(StrictModel):
    legacy_text: str


class Output(StrictModel):
    text: str


@block(id='rename-text', version='1.0.0', name='字段转换', description='将 legacyText 显式转换为 text')
def convert(value: Input) -> Output:
    return Output(text=value.legacy_text)
