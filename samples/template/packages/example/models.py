from pydantic import Field
from agent_platform.contracts.models import ModelRequest, ModelResponse
from agent_platform.contracts.packages import PackageBudget
from .contracts import Message


class Config(PackageBudget):
    instruction: str = Field(default='概括输入内容。', min_length=1)
    max_output_tokens: int = Field(default=512, gt=0)
