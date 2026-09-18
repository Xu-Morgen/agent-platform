"""草稿连接诊断契约；获取模型不要求预先知道模型名。"""
from typing import Literal
from pydantic import Field, model_validator
from .base import StrictModel
from .environments import ModelConnectionWrite
from .models import ModelUsage


class DiscoveryConnection(ModelConnectionWrite):
    kind: Literal['model'] = 'model'

    @model_validator(mode='after')
    def require_model(self):
        return self


class ModelListRequest(StrictModel):
    connection: DiscoveryConnection


class ConnectionTestRequest(StrictModel):
    connection: ModelConnectionWrite
    max_output_tokens: int = Field(default=256, ge=16, le=8192)


class ModelListResult(StrictModel):
    models: list[str]
    elapsed_ms: int = Field(ge=0)


class ConnectionTestResult(StrictModel):
    status: Literal['passed'] = 'passed'
    elapsed_ms: int = Field(ge=0)
    usage: ModelUsage
