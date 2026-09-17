"""按结构化控制流检查保证可用的端口，不执行模块。"""
from dataclasses import dataclass
from ..contracts.base import StrictModel
from ..contracts.flows import ModuleNode, IfNode, RepeatNode, WhileNode, ConstantValue
from ..contracts.errors import PlatformError
from pydantic import Field
from .compatibility import assignable, at_path, literal_schema, Incompatible


class ValidationIssue(StrictModel):
    code: str = 'CONTRACT_VALIDATION_ERROR'
    stage: str = 'flow.validation'
    reason: str
    field_path: list[str | int] = Field(default_factory=list)
    node_id: str | None = None
    source_node_id: str | None = None
    source_port: list[str | int] | None = None
    target_port: list[str | int] | None = None


class ValidationResult(StrictModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


@dataclass
class Port:
    schema: dict
    contract: str | None = None
    kind: str | None = None


def validate_flow(draft, catalog):
    issues = []
    def report(reason, path, node=None, source=None, target=None):
        issues.append(ValidationIssue(reason=reason, field_path=list(path), node_id=node,
            source_node_id=getattr(source, 'node_id', None), source_port=getattr(source, 'path', None), target_port=target))
    def contract(ref):
        return Port(catalog.contract(ref).schema, ref)
    def source_port(source, scope, carry):
        if isinstance(source, ConstantValue):
            return Port(literal_schema(source.value))
        if source.kind == 'input':
            port = contract(draft.input_contract)
        else:
            mapping = scope if source.kind == 'node' else carry
            if source.node_id not in mapping:
                raise Incompatible('引用未执行、前向或作用域外的节点/携带值')
            port = mapping[source.node_id]
        return Port(at_path(port.schema, source.path), port.contract if not source.path else None, port.kind)
    def bind(bindings, expected, scope, carry, path, node):
        assembled = {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
        targets = []
        for index, binding in enumerate(bindings):
            loc = (*path, index)
            try:
                target = binding.target
                if any(target[:len(old)] == old or old[:len(target)] == target for old in targets):
                    raise Incompatible('同一入口或父子入口存在重复来源')
                targets.append(target)
                port = source_port(binding.source, scope, carry)
                if not target:
                    assembled = port.schema
                else:
                    current = assembled
                    for i, key in enumerate(target):
                        if not isinstance(key, str):
                            raise Incompatible('数组输入请连接完整数组，不逐索引装配')
                        if key not in current['required']:
                            current['required'].append(key)
                        if i == len(target) - 1:
                            current['properties'][key] = port.schema
                        else:
                            current = current['properties'].setdefault(key, {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False})
                # 单条接线错误保留两端；整体装配另检查必填和多余字段。
                target_schema = expected.schema
                for key in target:
                    from .compatibility import resolve
                    target_schema = resolve(target_schema, expected.schema).get('properties', {}).get(key, {})
                assignable(port.schema, target_schema, target_root=expected.schema)
            except (Incompatible, PlatformError) as exc:
                report(str(exc), loc, node, binding.source, binding.target)
        try:
            assignable(assembled, expected.schema)
        except Incompatible as exc:
            report(str(exc), path, node)
    def condition(reference, scope, carry, path, node):
        port = source_port(reference, scope, carry)
        if reference.kind != 'node' or reference.path or port.kind != 'block':
            raise Incompatible('条件必须引用严格 bool 通用块的完整输出')
        assignable(port.schema, {'type': 'boolean'})
    def sequence(nodes, scope, carry, prefix):
        scope = dict(scope)
        for index, node in enumerate(nodes):
            path = (*prefix, index)
            try:
                if isinstance(node, ModuleNode):
                    view = catalog.get(node.artifact_ref)
                    if view.kind != node.kind:
                        raise Incompatible('节点类型与模块资源不符')
                    bind(node.inputs, contract(view.input_contract), scope, carry, (*path, 'inputs'), node.node_id)
                    port = contract(view.output_contract)
                    port.kind = node.kind
                elif isinstance(node, IfNode):
                    condition(node.condition, scope, carry, path, node.node_id)
                    port = contract(node.output_contract)
                    for name, branch in [('thenBranch', node.then_branch), ('elseBranch', node.else_branch)]:
                        child = sequence(branch.nodes, scope, carry, (*path, name, 'nodes'))
                        bind(branch.output, port, child, carry, (*path, name, 'output'), node.node_id)
                else:
                    port = contract(node.carry.contract)
                    bind(node.carry.initial, port, scope, carry, (*path, 'carry', 'initial'), node.node_id)
                    inner_carry = {**carry, node.node_id: port}
                    if isinstance(node, WhileNode):
                        condition_scope = sequence([node.condition], scope, inner_carry, (*path, 'condition'))
                        from ..contracts.flows import PortReference
                        condition(PortReference(kind='node', node_id=node.condition.node_id), condition_scope, inner_carry, path, node.node_id)
                    child = sequence(node.body, scope, inner_carry, (*path, 'body'))
                    bind(node.carry.update, port, child, inner_carry, (*path, 'carry', 'update'), node.node_id)
                scope[node.node_id] = port
            except (Incompatible, PlatformError) as exc:
                report(str(exc), path, node.node_id)
        return scope
    try:
        contract(draft.input_contract)
        output = contract(draft.output_contract)
        scope = sequence(draft.flow, {}, {}, ('flow',))
        bind(draft.output, output, scope, {}, ('output',), None)
    except PlatformError as exc:
        report(str(exc), ('inputContract',) if draft.input_contract not in catalog._contracts else ('outputContract',))
    return ValidationResult(valid=not issues, issues=issues)
