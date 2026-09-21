"""编辑器解释协议：输出只有说明和位置建议，没有可执行配置。"""
from typing import Literal
from pydantic import Field, JsonValue, model_validator
from .base import StrictModel
from .flows import ConnectionSelection
from .models import ModelUsage


class AdviceRequest(StrictModel):
    resource_id: str = Field(min_length=1)
    model: ConnectionSelection
    content: dict[str, JsonValue]


class Placement(StrictModel):
    node_id: str | None
    position: Literal['before', 'after', 'start']
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def anchor(self):
        if (self.position == 'start') != (self.node_id is None):
            raise ValueError('start 使用 null；before/after 必须引用当前草稿节点')
        return self


class ResourceAdvice(StrictModel):
    purpose: str = Field(min_length=1, max_length=4000)
    suitability: Literal['suitable', 'conditional', 'unsuitable', 'unknown']
    assessment: str = Field(min_length=1, max_length=4000)
    placements: list[Placement] = Field(max_length=8)
    requirements: list[str] = Field(max_length=12)


class AdviceResult(StrictModel):
    advice: ResourceAdvice
    usage: ModelUsage
    model: str
