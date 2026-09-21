"""拼图协议权威来源；只描述结构，执行与资源解析由后续层负责。"""
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit
from pydantic import Field, JsonValue, ValidationError, field_validator, model_validator
from .base import StrictModel
from .packages import Identifier
from .budgets import InstanceBudget, NodeBudget, PositiveInt, DEFAULT_CONTRACT_RETRY_LIMIT

ResourceId = Annotated[str, Field(min_length=1)]


class PortReference(StrictModel):
    kind: Literal['input', 'node', 'carry', 'item']
    node_id: Identifier | None = None

    @model_validator(mode='after')
    def node_required(self):
        if (self.kind == 'input') != (self.node_id is None):
            raise ValueError('node/carry/item 引用必须声明 nodeId；input 不声明 nodeId')
        return self


class ConstantValue(StrictModel):
    kind: Literal['constant']
    value: JsonValue


class PortBinding(StrictModel):
    source: Annotated[PortReference | ConstantValue, Field(discriminator='kind')]


class ConnectionSelection(StrictModel):
    environment_id: Identifier
    connection_id: Identifier


class APISelection(ConnectionSelection):
    path: str = Field(min_length=1, description='API Base URL 下的相对请求路径')

    @field_validator('path')
    @classmethod
    def relative_path(cls, value):
        reason = 'API 路径须为连接下的相对路径，不包含查询字符串、片段或目录回退'
        try:
            parsed = urlsplit(value)
            decoded = unquote(value)
            if (parsed.scheme or parsed.netloc or '?' in value or '#' in value
                    or decoded.startswith('//') or '\\' in decoded
                    or any(char.isspace() or ord(char) < 32 for char in value)
                    or any(part in ('.', '..') for part in decoded.split('/'))):
                raise ValueError(reason)
        except ValueError:
            raise ValueError(reason) from None
        return value


class NodeConfiguration(StrictModel):
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    budget: NodeBudget | None = None
    model: ConnectionSelection
    max_output_tokens: PositiveInt = 512


class BlockConfiguration(StrictModel):
    api: APISelection


class ModuleNode(StrictModel):
    node_id: Identifier
    kind: Literal['block', 'package']
    artifact_ref: ResourceId
    references: list[PortReference] | None = None

    @model_validator(mode='after')
    def unique_references(self):
        if self.references is not None:
            keys = [(ref.kind, ref.node_id) for ref in self.references]
            if len(keys) != len(set(keys)):
                raise ValueError('参考列表不得重复绑定同一来源')
        return self


class Branch(StrictModel):
    nodes: list['FlowNode'] = Field(default_factory=list)
    output: list[PortBinding]


class ServiceNode(StrictModel):
    """配置者选择已保存实例；入口为完整业务数据，不开放跨服务参考。"""
    node_id: Identifier
    kind: Literal['service']
    service_id: Identifier
    instance_id: Identifier


class IfNode(StrictModel):
    node_id: Identifier
    kind: Literal['if']
    condition: ModuleNode
    output_contract: ResourceId
    then_branch: Branch
    else_branch: Branch

    @model_validator(mode='after')
    def boolean_block(self):
        if self.condition.kind != 'block':
            raise ValueError('if 条件必须是通用块')
        return self


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


class SwitchCase(Branch):
    value: str


class SwitchNode(StrictModel):
    node_id: Identifier
    kind: Literal['switch']
    router: ModuleNode
    output_contract: ResourceId
    cases: list[SwitchCase] = Field(min_length=1)

    @model_validator(mode='after')
    def routing_block(self):
        if self.router.kind != 'block':
            raise ValueError('switch 路由必须是 Python 通用块')
        values = [case.value for case in self.cases]
        if len(set(values)) != len(values):
            raise ValueError('switch 分支枚举值不得重复')
        return self


class ForeachNode(StrictModel):
    node_id: Identifier
    kind: Literal['foreach']
    source: PortReference
    array_path: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    max_items: Annotated[int, Field(gt=0)]
    item_output_contract: ResourceId
    body: list['FlowNode'] = Field(min_length=1)


FlowNode = Annotated[ModuleNode | ServiceNode | IfNode | RepeatNode | WhileNode | ForeachNode | SwitchNode, Field(discriminator='kind')]
for _model in (Branch, SwitchCase, SwitchNode, RepeatNode, WhileNode, ForeachNode):
    _model.model_rebuild()


def walk_nodes(nodes, prefix=('flow',)):
    for index, node in enumerate(nodes):
        path = (*prefix, index)
        yield node, path
        if isinstance(node, IfNode):
            yield node.condition, (*path, 'condition')
            for branch in ('then_branch', 'else_branch'):
                yield from walk_nodes(getattr(node, branch).nodes, (*path, 'thenBranch' if branch == 'then_branch' else 'elseBranch', 'nodes'))
        elif isinstance(node, SwitchNode):
            yield node.router, (*path, 'router')
            for case_index, case in enumerate(node.cases):
                yield from walk_nodes(case.nodes, (*path, 'cases', case_index, 'nodes'))
        elif isinstance(node, (RepeatNode, WhileNode, ForeachNode)):
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
    node_configurations: dict[Identifier, NodeConfiguration | BlockConfiguration] = Field(default_factory=dict)
    budget: InstanceBudget | None = None
    retry_limit: Annotated[int, Field(ge=0, le=1000)] = DEFAULT_CONTRACT_RETRY_LIMIT
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
