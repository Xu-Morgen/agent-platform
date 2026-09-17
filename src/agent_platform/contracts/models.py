"""平台模型协议：结构化文本交互、显式输出限额和计量质量。"""
from typing import Literal, Protocol
from pydantic import Field, JsonValue, model_validator
from .base import StrictModel

Measurement = Literal['exact', 'upper_bound', 'estimated', 'unsupported']


class ModelMessage(StrictModel):
    role: Literal['system', 'user', 'assistant']
    content: str


class ModelRequest(StrictModel):
    messages: list[ModelMessage] = Field(min_length=1)
    max_output_tokens: int = Field(gt=0)


class ModelUsage(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    quality: Measurement
    source: str

    @model_validator(mode='after')
    def counts(self):
        if self.quality != 'unsupported' and (self.input_tokens is None or self.output_tokens is None):
            raise ValueError('可用计量必须提供输入和输出计数')
        return self


class ModelResponse(StrictModel):
    output: JsonValue
    usage: ModelUsage


class ModelCapabilities(StrictModel):
    protocol: str
    input_preflight: Measurement
    response_usage: Measurement
    missing_usage: Measurement
    output_limit: bool
    hidden_tokens_verified: bool
    strict_total_limit: bool
    closes_local_transport: bool


class ModelAdapter(Protocol):
    capabilities: ModelCapabilities

    async def preflight(self, connection, request: ModelRequest) -> ModelUsage: ...
    async def invoke(self, connection, request: ModelRequest) -> ModelResponse: ...
    async def close(self) -> None: ...
