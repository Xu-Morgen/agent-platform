from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.packages import PackageBudget

class Message(StrictModel):
    text: str

class Config(PackageBudget):
    prefix: str = '合成'
