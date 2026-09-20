"""最小业务契约：symbol 填 Text；服务输入仍是业务 JSON，NodeInput 由平台封装。"""
from agent_platform.contracts.base import StrictModel


class Text(StrictModel):
    text: str
