from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.models import ModelRequest, ModelResponse

class Message(StrictModel):
    text: str
