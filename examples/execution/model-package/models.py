from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.packages import PackageBudget
from agent_platform.contracts.models import ModelRequest, ModelResponse

class Message(StrictModel):
    text: str

class Config(PackageBudget):
    max_output_tokens: int = 128
