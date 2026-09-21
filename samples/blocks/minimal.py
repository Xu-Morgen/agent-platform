"""最小通用块：去掉文本首尾空白；加载本文件即可。"""
from pydantic import Field
from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput


class Text(StrictModel):
    """只有 text 的最小文本契约，适合演示原样传递、文本整理或模型回复。"""
    text: str = Field(description='待处理或处理后的完整文本；允许空字符串。相邻步骤传递整个 text 对象。')


@block(id='sample-trim', version='3.0.0', name='去掉首尾空白', description='接收 text 对象，去掉文本首尾空白后仍返回 text；不改变中间内容，不调用模型或外部 API。适合放在文本输入后、模型包前。无参考输入。')
def trim(value: NodeInput[Text, tuple[()]]) -> Text:
    return Text(text=value.primary.text.strip())
