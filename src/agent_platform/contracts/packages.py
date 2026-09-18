"""声明式 Prompt 包：只维护契约、Prompt 和可选节点预算默认值。"""
from typing import Annotated
from pydantic import Field
from .base import StrictModel
from .budgets import NodeBudget

Identifier = Annotated[str, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')]
SymbolReference = Annotated[str, Field(pattern=r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$')]
Version = Annotated[str, Field(pattern=r'^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$')]


class ContractReferences(StrictModel):
    input: SymbolReference
    output: SymbolReference
    configuration: SymbolReference | None = None


class PackageManifest(StrictModel):
    package_id: Identifier
    version: Version
    name: str = Field(min_length=1)
    description: str = ''
    contract_refs: ContractReferences
    prompt: str = Field(default='prompt.txt', min_length=1)
    budget_defaults: NodeBudget | None = None
