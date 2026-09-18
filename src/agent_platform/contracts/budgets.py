"""节点和任务的执行预算，与业务参数契约独立。"""
from typing import Annotated
from pydantic import Field
from .base import StrictModel

PositiveInt = Annotated[int, Field(gt=0)]


class NodeBudget(StrictModel):
    loop_limit: PositiveInt = 1
    token_limit: PositiveInt = 32768


class InstanceBudget(NodeBudget):
    strict_token_limit: bool = True
