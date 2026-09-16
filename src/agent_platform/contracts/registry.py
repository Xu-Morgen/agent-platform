from typing import Literal
from pydantic import Field, JsonValue
from .base import StrictModel
from .instances import InstanceDefinition


class LoadRequest(StrictModel):
    kind: Literal['package', 'block', 'instance']
    path: str = Field(min_length=1)


class LoadResult(StrictModel):
    kind: Literal['package', 'block', 'instance']
    id: str
    version: str | None = None
    load_id: str | None = None
    digest: str
    definition: InstanceDefinition | None = None
    schemas: dict[str, JsonValue]
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    budget_defaults: dict[str, JsonValue] = Field(default_factory=dict)
