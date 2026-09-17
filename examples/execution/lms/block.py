from agent_platform.blocks.lms import LMSResponse, unwrap
from agent_platform.contracts.base import StrictModel

class Message(StrictModel):
    text: str

def execute(value):
    return unwrap(value, Message)
