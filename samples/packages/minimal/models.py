from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput


class Text(StrictModel):
    text: str


class Entry(NodeInput[Text, tuple[()]]):
    """首节点默认零参考；接在其他节点后时选择高级空列表。"""
