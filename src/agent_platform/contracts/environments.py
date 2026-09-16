"""环境写入与公开响应分离，凭据原值仅允许进入写请求。"""
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, SecretStr, field_validator, model_validator
from .base import StrictModel
from .packages import Identifier, PositiveInt


class Connection(StrictModel):
    connection_id: Identifier
    kind: Literal['model', 'api']
    base_url: str
    model: str | None = Field(default=None, min_length=1)
    timeout_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)
    credential_ref: str | None = None

    @field_validator('base_url')
    @classmethod
    def safe_url(cls, value):
        try:
            url = urlsplit(value)
            port = url.port
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError()
            if any(char.isspace() for char in value):
                raise ValueError()
        except ValueError:
            raise ValueError('连接地址须为无认证信息和查询参数的 HTTP(S) URL') from None
        return value

    @model_validator(mode='after')
    def require_model(self):
        if self.kind == 'model' and not self.model:
            raise ValueError('模型连接必须指定模型标识')
        return self


class ConnectionWrite(Connection):
    credential: SecretStr | None = None

    @model_validator(mode='after')
    def credential_choice(self):
        if self.credential is not None:
            if self.credential_ref is not None or not self.credential.get_secret_value().strip():
                raise ValueError('填写凭据或引用其中一种，凭据不得为空')
        return self


class EnvironmentWrite(StrictModel):
    name: str = Field(min_length=1)
    connections: list[ConnectionWrite] = Field(min_length=1)

    @field_validator('connections')
    @classmethod
    def unique_connections(cls, values):
        if len({c.connection_id for c in values}) != len(values):
            raise ValueError('连接标识重复')
        return values


class Environment(StrictModel):
    environment_id: Identifier
    revision: PositiveInt
    name: str
    connections: list[Connection]
