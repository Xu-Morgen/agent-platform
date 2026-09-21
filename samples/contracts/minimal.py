"""最小业务契约：symbol 填 Text；服务输入仍是业务 JSON，NodeInput 由平台封装。"""
from pydantic import Field
from agent_platform.contracts.base import StrictModel


class Text(StrictModel):
    """只有 text 的最小文本契约，适合演示原样传递、文本整理或模型回复。"""
    text: str = Field(description='待处理或处理后的完整文本；允许空字符串。相邻步骤传递整个 text 对象。')
