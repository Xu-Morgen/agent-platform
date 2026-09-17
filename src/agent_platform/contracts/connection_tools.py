"""草稿连接诊断契约；获取模型不要求预先知道模型名。"""
from typing import Literal
from pydantic import Field, model_validator
from .base import StrictModel
from .environments import ConnectionWrite
from .models import ModelUsage


class DiscoveryConnection(ConnectionWrite):
    kind: Literal['model'] = 'model'

    @model_validator(mode='after')
    def require_model(self):
        return self


class ModelListRequest(StrictModel):
    connection: DiscoveryConnection


class ConnectionTestRequest(StrictModel):
    connection: ConnectionWrite
    max_output_tokens: int = Field(default=256, ge=16, le=8192)

    @model_validator(mode='after')
    def model_only(self):
        if self.connection.kind != 'model':
            raise ValueError('连接测试仅支持模型连接')
        return self


class ModelListResult(StrictModel):
    models: list[str]
    elapsed_ms: int = Field(ge=0)


class ConnectionTestResult(StrictModel):
    status: Literal['passed'] = 'passed'
    elapsed_ms: int = Field(ge=0)
    usage: ModelUsage
