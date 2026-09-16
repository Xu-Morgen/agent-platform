"""业务包声明；仅描述契约与依赖，不加载或执行业务。"""
from typing import Annotated, Literal
from pydantic import Field
from .base import StrictModel

Identifier = Annotated[str, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')]
SymbolReference = Annotated[str, Field(pattern=r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$')]
Version = Annotated[str, Field(pattern=r'^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$')]
PositiveInt = Annotated[int, Field(gt=0)]


class PackageBudget(StrictModel):
    loop_limit: PositiveInt = 1
    token_limit: PositiveInt = 32768


class InstanceBudget(PackageBudget):
    strict_token_limit: bool = True


class ContractReferences(StrictModel):
    input: SymbolReference
    output: SymbolReference
    configuration: SymbolReference


class CapabilityRequirement(StrictModel):
    capability_id: Identifier
    kind: Literal['model', 'api', 'block']
    input_model: SymbolReference
    output_model: SymbolReference


class RuntimeRequirements(StrictModel):
    python: str = Field(min_length=1)
    platform_api: Literal[1]
    dependencies: list[Annotated[str, Field(min_length=1)]]


class PackageManifest(StrictModel):
    package_id: Identifier
    version: Version
    name: str = Field(min_length=1)
    description: str
    entry: SymbolReference
    contract_refs: ContractReferences
    runtime_requirements: RuntimeRequirements
    required_capabilities: list[CapabilityRequirement]
    budget_defaults: PackageBudget
