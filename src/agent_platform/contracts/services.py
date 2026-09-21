from typing import Literal
from pydantic import Field, JsonValue
from .base import StrictModel
from .flows import FlowDraft
from .packages import Identifier
from .budgets import PositiveInt, InstanceBudget


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


class ServiceComponent(StrictModel):
    service_id: Identifier
    instance_id: Identifier
    name: str
    version: str
    current: bool
    input_contract: str
    output_contract: str
    schemas: dict[str, JsonValue]
    budget: InstanceBudget | None


class FlowHistory(StrictModel):
    version: VersionView
    flow: FlowDraft | dict[str, JsonValue]
    executable: bool = True
    upgrade_message: str | None = None
    compiler_version: str
    input: dict[str, JsonValue]
    output: dict[str, JsonValue]
    examples: list[JsonValue]
    configuration: dict[str, JsonValue]
    children: dict[str, JsonValue] = Field(default_factory=dict)
