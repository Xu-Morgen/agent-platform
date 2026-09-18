"""按结构化控制流检查保证可用的端口，不执行模块。"""
from dataclasses import dataclass
from ..contracts.base import StrictModel
from ..contracts.flows import ModuleNode, IfNode, RepeatNode, WhileNode, ConstantValue
from ..contracts.errors import PlatformError, ValidationIssue
from pydantic import Field, ValidationError
from .compatibility import assignable, Incompatible


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
        if source.path:
            raise Incompatible('平台只传递完整数据；字段选取或改名请添加通用块处理')
        if source.kind == 'input':
            port = contract(draft.input_contract)
        else:
            mapping = scope if source.kind == 'node' else carry
            if source.node_id not in mapping:
                raise Incompatible('引用未执行、前向或作用域外的节点/携带值')
            port = mapping[source.node_id]
        return port
    def bind(bindings, expected, scope, carry, path, node):
        if len(bindings) != 1:
            report('请选择一个完整数据来源；字段合并或转换请添加通用块处理', path, node)
            return
        binding = bindings[0]
        try:
            if binding.target:
                raise Incompatible('平台不支持目标字段映射；请添加通用块输出符合接收方契约的完整数据')
            if isinstance(binding.source, ConstantValue):
                try:
                    catalog.contract(expected.contract).adapter.validate_python(binding.source.value, strict=True)
                except ValidationError as exc:
                    from ..validation_issues import validation_exception
                    raise validation_exception(exc, stage='flow.constant') from None
            else:
                port = source_port(binding.source, scope, carry)
                assignable(port.schema, expected.schema)
        except (Incompatible, PlatformError) as exc:
            report(str(exc) + '；输入输出契约必须兼容，需要转换时请添加通用块。',
                   (*path, 0), node, binding.source, binding.target)
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
