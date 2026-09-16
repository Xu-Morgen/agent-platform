from agent_platform.contracts.base import StrictModel

class Message(StrictModel):
    text: str

def identity(value):
    return value
