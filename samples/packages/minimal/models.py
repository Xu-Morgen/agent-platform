from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.models import ModelRequest, ModelResponse
from agent_platform.contracts.packages import PackageBudget


class Text(StrictModel):
    text: str


class Config(PackageBudget):
    pass  # 最小包只有继承得到的 loopLimit 与 tokenLimit。
