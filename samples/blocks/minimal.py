"""最小通用块：去掉文本首尾空白；加载本文件即可。"""
from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput


class Text(StrictModel):
    text: str


@block(id='sample-trim', version='2.0.0', name='去掉首尾空白')
def trim(value: NodeInput[Text, tuple[()]]) -> Text:
    return Text(text=value.primary.text.strip())
