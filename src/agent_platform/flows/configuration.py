"""nodeId 独立配置校验；只读取环境，不占用环境或调用能力。"""
from pydantic import ValidationError
from ..contracts.flows import ModuleNode, NodeConfiguration, walk_nodes
from ..contracts.base import StrictModel
from ..contracts.errors import PlatformError
from ..contracts.budgets import NodeBudget
from .validation import ValidationIssue, ValidationResult
from .compatibility import Incompatible


class NodeValidationRequest(StrictModel):
    node: ModuleNode
    configuration: NodeConfiguration | None = None
    strict_token_limit: bool = True


class NodeValidationResult(ValidationResult):
    configuration: NodeConfiguration | None = None


def validate_node(request, catalog, environments):
    node, config = request.node, request.configuration
    issues = []
    normalized = None
    def issue(reason, path=(), code='CONFIGURATION_ERROR'):
        issues.append(ValidationIssue(code=code, stage='node.configuration', reason=reason,
            node_id=node.node_id, field_path=['nodeConfigurations', node.node_id, *path]))
    try:
        view = catalog.get(node.artifact_ref)
        if view.kind != node.kind:
            issue('节点类型与模块资源不符', ['artifactRef'])
        elif node.kind == 'block':
            if config is not None:
                issue('通用块不配置模型预算或环境')
        elif config is None:
            issue('缺少业务包节点参数、预算和能力配置')
        else:
            artifact = catalog.artifact(node.artifact_ref)
            reference = artifact.manifest.contract_refs.configuration
            model = artifact.content.load(reference) if reference else StrictModel
            try:
                value = model.model_validate(config.parameters, strict=True)
                normalized = config.model_copy(update={
                    'parameters': value.model_dump(mode='json', by_alias=True),
                    'budget': config.budget or artifact.manifest.budget_defaults or NodeBudget(),
                }, deep=True)
            except ValidationError as exc:
                from ..validation_issues import issues_from_errors
                issues.extend(issues_from_errors(exc.errors(), stage='node.configuration',
                    prefix=['nodeConfigurations', node.node_id, 'parameters'], node_id=node.node_id, code='CONFIGURATION_ERROR'))
            try:
                environment = environments.get(config.model.environment_id)
                connection = next((c for c in environment.connections if c.connection_id == config.model.connection_id), None)
                if connection is None or connection.kind != 'model':
                    raise Incompatible('请选择有效的模型连接')
                if connection.credential_ref:
                    environments.credentials.get(connection.credential_ref)
                if request.strict_token_limit:
                    issue('所选模型适配器不能保证严格 token 上限，请明确选择非严格模式或支持该能力的适配器', ['model'], 'TOKEN_ACCOUNTING_UNSUPPORTED')
            except (PlatformError, Incompatible) as exc:
                issue(str(exc), ['model'])
    except PlatformError as exc:
        issue(str(exc), ['artifactRef'], exc.error.code)
    return NodeValidationResult(valid=not issues, issues=issues, configuration=normalized if not issues else None)


def validate_configurations(draft, catalog, environments):
    issues = []
    nodes = {node.node_id: node for node, _ in walk_nodes(draft.flow)}
    packages = [node for node in nodes.values() if isinstance(node, ModuleNode) and node.kind == 'package']
    if packages and draft.budget is None:
        issues.append(ValidationIssue(code='CONFIGURATION_ERROR', reason='含业务包流程必须配置任务全局预算', field_path=['budget']))
    for key in draft.node_configurations.keys() - {n.node_id for n in packages}:
        issues.append(ValidationIssue(code='CONFIGURATION_ERROR', reason='配置必须对应业务包节点', node_id=key, field_path=['nodeConfigurations', key]))
    for node in nodes.values():
        if isinstance(node, ModuleNode):
            result = validate_node(NodeValidationRequest(node=node, configuration=draft.node_configurations.get(node.node_id),
                strict_token_limit=draft.budget.strict_token_limit if draft.budget else True), catalog, environments)
            issues.extend(result.issues)
    return ValidationResult(valid=not issues, issues=issues)
