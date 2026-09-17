"""最小独立契约：加载本文件，symbol 填 Text。"""
from agent_platform.contracts.base import StrictModel


class Text(StrictModel):
    text: str
