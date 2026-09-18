"""拼图协议权威来源；只描述结构，执行与资源解析由后续层负责。"""
from typing import Annotated, Literal
from pydantic import Field, JsonValue, ValidationError, model_validator
from .base import StrictModel
from .packages import Identifier
from .budgets import InstanceBudget, NodeBudget, PositiveInt

ResourceId = Annotated[str, Field(min_length=1)]
Path = list[str | Annotated[int, Field(ge=0)]]


class PortReference(StrictModel):
    kind: Literal['input', 'node', 'carry']
    node_id: Identifier | None = None
    path: Path = Field(default_factory=list)

    @model_validator(mode='after')
    def node_required(self):
        if (self.kind == 'input') != (self.node_id is None):
            raise ValueError('node/carry 引用必须声明 nodeId；input 不声明 nodeId')
        return self


class ConstantValue(StrictModel):
    kind: Literal['constant']
    value: JsonValue


class PortBinding(StrictModel):
    target: Path = Field(default_factory=list)
    source: Annotated[PortReference | ConstantValue, Field(discriminator='kind')]


class ModelSelection(StrictModel):
    environment_id: Identifier
    connection_id: Identifier


class NodeConfiguration(StrictModel):
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    budget: NodeBudget | None = None
    model: ModelSelection
    max_output_tokens: PositiveInt = 512


class ModuleNode(StrictModel):
    node_id: Identifier
    kind: Literal['block', 'package']
    artifact_ref: ResourceId
    inputs: list[PortBinding] = Field(default_factory=list)


class Branch(StrictModel):
    nodes: list['FlowNode'] = Field(default_factory=list)
    output: list[PortBinding]


class IfNode(StrictModel):
    node_id: Identifier
    kind: Literal['if']
    condition: PortReference
    output_contract: ResourceId
    then_branch: Branch
    else_branch: Branch


class LoopCarry(StrictModel):
    contract: ResourceId
    initial: list[PortBinding]
    update: list[PortBinding]


class RepeatNode(StrictModel):
    node_id: Identifier
    kind: Literal['repeat']
    count: Annotated[int, Field(ge=0)]
    carry: LoopCarry
    body: list['FlowNode'] = Field(default_factory=list)


class WhileNode(StrictModel):
    node_id: Identifier
    kind: Literal['while']
    max_iterations: Annotated[int, Field(gt=0)]
    condition: ModuleNode
    carry: LoopCarry
    body: list['FlowNode'] = Field(default_factory=list)

    @model_validator(mode='after')
    def boolean_block(self):
        if self.condition.kind != 'block':
            raise ValueError('while 条件必须是通用块')
        return self


FlowNode = Annotated[ModuleNode | IfNode | RepeatNode | WhileNode, Field(discriminator='kind')]
for _model in (Branch, RepeatNode, WhileNode):
    _model.model_rebuild()


def walk_nodes(nodes, prefix=('flow',)):
    for index, node in enumerate(nodes):
        path = (*prefix, index)
        yield node, path
        if isinstance(node, IfNode):
            for branch in ('then_branch', 'else_branch'):
                yield from walk_nodes(getattr(node, branch).nodes, (*path, 'thenBranch' if branch == 'then_branch' else 'elseBranch', 'nodes'))
        elif isinstance(node, (RepeatNode, WhileNode)):
            if isinstance(node, WhileNode):
                yield node.condition, (*path, 'condition')
            yield from walk_nodes(node.body, (*path, 'body'))


class FlowExample(StrictModel):
    name: str
    input: JsonValue


class FlowDraft(StrictModel):
    draft_id: Identifier | None = None
    name: str = Field(min_length=1)
    input_contract: ResourceId
    output_contract: ResourceId
    flow: list[FlowNode]
    output: list[PortBinding]
    node_configurations: dict[Identifier, NodeConfiguration] = Field(default_factory=dict)
    budget: InstanceBudget | None = None
    examples: list[FlowExample] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_nodes(self):
        seen, errors = set(), []
        for node, path in walk_nodes(self.flow):
            if node.node_id in seen:
                errors.append({'type': 'value_error', 'loc': (*path, 'nodeId'),
                               'ctx': {'error': ValueError('nodeId 重复')}})
            seen.add(node.node_id)
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self
