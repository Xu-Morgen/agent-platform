"""父子进程 JSON Lines 控制协议 v1。"""
from typing import Annotated, Literal
from pydantic import Field, TypeAdapter
from .base import StrictModel
from .errors import ErrorResponse


class Ready(StrictModel):
    protocol_version: Literal[1] = 1
    type: Literal['ready'] = 'ready'
    address: str = Field(pattern=r'^http://(?:[0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$')


class StartupError(StrictModel):
    protocol_version: Literal[1] = 1
    type: Literal['startupError'] = 'startupError'
    error: ErrorResponse


class Shutdown(StrictModel):
    protocol_version: Literal[1] = 1
    type: Literal['shutdown'] = 'shutdown'
    reason: Literal['APPLICATION_EXIT'] = 'APPLICATION_EXIT'


ControlMessage = Annotated[Ready | StartupError | Shutdown, Field(discriminator='type')]
CONTROL = TypeAdapter(ControlMessage)


def parse_control(data: str) -> Ready | StartupError | Shutdown:
    # 在线路上要求显式版本，不允许默认值掩盖缺失的协议头。
    import json
    value = json.loads(data)
    if not isinstance(value, dict) or type(value.get('protocolVersion')) is not int or value['protocolVersion'] != 1:
        raise ValueError('控制协议版本必须显式为整数 1')
    return CONTROL.validate_python(value, strict=True)
