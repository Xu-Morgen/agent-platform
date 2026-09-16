"""父子进程 JSON Lines 控制协议 v1。"""
from typing import Annotated, Literal
from pydantic import Field, TypeAdapter
from .base import StrictModel
from .errors import ErrorResponse


class ControlEnvelope(StrictModel):
    protocol_version: int = Field(ge=1, le=1)


class Ready(ControlEnvelope):
    type: Literal['ready']
    address: str = Field(pattern=r'^http://(?:[0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$')


class StartupError(ControlEnvelope):
    type: Literal['startupError']
    error: ErrorResponse


class Shutdown(ControlEnvelope):
    type: Literal['shutdown']
    reason: Literal['APPLICATION_EXIT'] = 'APPLICATION_EXIT'


ControlMessage = Annotated[Ready | StartupError | Shutdown, Field(discriminator='type')]
CONTROL = TypeAdapter(ControlMessage)


def parse_control(data: str) -> Ready | StartupError | Shutdown:
    return CONTROL.validate_json(data, strict=True)
