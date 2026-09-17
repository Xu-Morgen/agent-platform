from typing import Literal
from pydantic import Field, JsonValue
from .base import StrictModel


class CatalogLoad(StrictModel):
    kind: Literal['package', 'block', 'contract']
    path: str = Field(min_length=1)
    symbol: str | None = Field(default=None, pattern=r'^[A-Za-z_]\w*$')


class CatalogResource(StrictModel):
    resource_id: str
    kind: Literal['package', 'block', 'contract']
    name: str
    description: str = ''
    version: str
    digest: str
    input_contract: str | None = None
    output_contract: str | None = None
    configuration_contract: str | None = None
    schemas: dict[str, JsonValue] = Field(default_factory=dict)
    required_capabilities: list[dict[str, JsonValue]] = Field(default_factory=list)
