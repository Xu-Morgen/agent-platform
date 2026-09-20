"""按结构化控制流检查保证可用的端口，不执行模块。"""
from dataclasses import dataclass
from ..contracts.base import StrictModel
from ..contracts.flows import ModuleNode, IfNode, RepeatNode, WhileNode, ConstantValue, PortReference
from ..contracts.errors import PlatformError, ValidationIssue
from pydantic import Field, ValidationError
from .compatibility import assignable, Incompatible
from ..contracts.node_input import input_schemas


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
    def report(reason, path, node=None, source=None):
        issues.append(ValidationIssue(reason=reason, field_path=list(path), node_id=node,
            source_node_id=getattr(source, 'node_id', None)))
    def contract(ref):
        return Port(catalog.contract(ref).schema, ref)
    def source_port(source, scope, carry):
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
                   (*path, 0), node, binding.source)
    def module(node, primary, defaults, scope, carry, path, *, condition=False):
        view = catalog.get(node.artifact_ref)
        if view.kind != node.kind:
            raise Incompatible('节点类型与模块资源不符')
        expected, slots = input_schemas(contract(view.input_contract).schema)
        assignable(primary.schema, contract(view.primary_contract).schema if view.primary_contract else expected)
        references = defaults if node.references is None else [source_port(ref, scope, carry) for ref in node.references]
        if len(references) != len(slots):
            raise Incompatible(f'参考数量不符：声明 {len(slots)} 项，实际 {len(references)} 项；请配置高级参考')
        for index, (reference, slot) in enumerate(zip(references, slots)):
            try:
                assignable(reference.schema, slot)
            except Incompatible as exc:
                raise Incompatible(f'参考位置 {index}：{exc}') from None
        port = contract(view.output_contract)
        port.kind = node.kind
        if condition:
            assignable(port.schema, {'type': 'boolean'})
        return port

    def sequence(nodes, scope, carry, prefix, incoming, defaults=()):
        scope = dict(scope)
        primary = source_port(incoming, scope, carry)
        for index, node in enumerate(nodes):
            path = (*prefix, index)
            try:
                if isinstance(node, ModuleNode):
                    port = module(node, primary, defaults, scope, carry, path)
                    primary = contract(catalog.get(node.artifact_ref).primary_contract)
                elif isinstance(node, IfNode):
                    module(node.condition, primary, defaults, scope, carry, (*path, 'condition'), condition=True)
                    port = contract(node.output_contract)
                    previous = PortReference(kind='node', node_id=nodes[index - 1].node_id) if index else incoming
                    for name, branch in [('thenBranch', node.then_branch), ('elseBranch', node.else_branch)]:
                        child = sequence(branch.nodes, scope, carry, (*path, name, 'nodes'), previous, defaults)
                        bind(branch.output, port, child, carry, (*path, name, 'output'), node.node_id)
                else:
                    port = contract(node.carry.contract)
                    bind(node.carry.initial, port, scope, carry, (*path, 'carry', 'initial'), node.node_id)
                    primary = port
                    inner_carry = {**carry, node.node_id: port}
                    if isinstance(node, WhileNode):
                        module(node.condition, port, [], scope, inner_carry, (*path, 'condition'), condition=True)
                    child = sequence(node.body, scope, inner_carry, (*path, 'body'), PortReference(kind='carry', node_id=node.node_id))
                    bind(node.carry.update, port, child, inner_carry, (*path, 'carry', 'update'), node.node_id)
                scope[node.node_id] = port
                defaults, primary = [primary], port
            except (Incompatible, PlatformError) as exc:
                report(str(exc), path, node.node_id)
        return scope
    try:
        if contract(draft.input_contract).schema.get('x-node-input-version'):
            report('服务输入使用业务契约（primaryContract），NodeInput 由平台封装', ('inputContract',))
        output = contract(draft.output_contract)
        scope = sequence(draft.flow, {}, {}, ('flow',), PortReference(kind='input'))
        if not draft.flow:
            report('流程至少需要一个业务包或通用块，才能返回最后一步的输出', ('flow',))
        elif draft.flow[-1].node_id in scope:
            last = draft.flow[-1]
            try:
                assignable(scope[last.node_id].schema, output.schema)
            except Incompatible as exc:
                report('最后一步输出与输出契约不兼容：' + str(exc) + '；请添加通用块完成转换。',
                       ('outputContract',), source=PortReference(kind='node', node_id=last.node_id))
    except PlatformError as exc:
        report(str(exc), ('inputContract',) if draft.input_contract not in catalog._contracts else ('outputContract',))
    return ValidationResult(valid=not issues, issues=issues)
