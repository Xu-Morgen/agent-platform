from typing import Literal
from pydantic import Field, JsonValue
from .base import StrictModel
from .instances import InstanceDefinition
from .packages import Identifier, PositiveInt


class ServiceWrite(StrictModel):
    name: str = Field(min_length=1)
    definition_load_id: Identifier
    definition: InstanceDefinition


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
    definition: InstanceDefinition
    definition_load_id: Identifier
    configuration: dict[str, JsonValue]
