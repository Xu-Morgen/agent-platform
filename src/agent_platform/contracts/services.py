from typing import Literal
from pydantic import Field, JsonValue
from .base import StrictModel
from .flows import FlowDraft
from .packages import Identifier
from .budgets import PositiveInt


class ServiceWrite(StrictModel):
    name: str = Field(min_length=1)
    flow: FlowDraft


class VersionView(StrictModel):
    instance_id: Identifier
    revision: PositiveInt
    version: str
    change_kind: Literal['initial', 'minor', 'major', 'breaking']
    content_digest: str


class ServiceView(StrictModel):
    service_id: Identifier
    name: str
    active_instance_id: Identifier
    current: VersionView


class ServiceSchema(StrictModel):
    service: ServiceView
    input: dict[str, JsonValue]
    output: dict[str, JsonValue]
    examples: list[JsonValue]
    flow: FlowDraft
    compiler_version: str
    configuration: dict[str, JsonValue]
    configuration_schemas: dict[str, JsonValue]


class ActivateRequest(StrictModel):
    instance_id: Identifier


class FlowHistory(StrictModel):
    version: VersionView
    flow: FlowDraft
    compiler_version: str
    input: dict[str, JsonValue]
    output: dict[str, JsonValue]
    examples: list[JsonValue]
    configuration: dict[str, JsonValue]
