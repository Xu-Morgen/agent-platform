from pydantic import Field
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput


class Text(StrictModel):
    """只有 text 的最小文本契约，适合演示原样传递、文本整理或模型回复。"""
    text: str = Field(description='待处理或处理后的完整文本；允许空字符串。相邻步骤传递整个 text 对象。')


class Entry(NodeInput[Text, tuple[()]]):
    """首节点默认零参考；接在其他节点后时选择高级空列表。"""
