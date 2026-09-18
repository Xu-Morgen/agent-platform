"""包只绑定模型，声明 API 能力的通用块只绑定 API；预检不发送请求。"""
from pydantic import ValidationError
from ..contracts.flows import ModuleNode, NodeConfiguration, BlockConfiguration, walk_nodes
from ..contracts.base import StrictModel
from ..contracts.errors import PlatformError
from ..contracts.budgets import NodeBudget
from .validation import ValidationIssue, ValidationResult
from .compatibility import Incompatible


class NodeValidationRequest(StrictModel):
    node: ModuleNode
    configuration: NodeConfiguration | BlockConfiguration | None = None


class NodeValidationResult(ValidationResult):
    configuration: NodeConfiguration | BlockConfiguration | None = None


def validate_node(request, catalog, environments):
    node, config = request.node, request.configuration
    issues = []
    normalized = None

    def issue(reason, path=(), code='CONFIGURATION_ERROR'):
        issues.append(ValidationIssue(code=code, stage='node.configuration', reason=reason,
            node_id=node.node_id, field_path=['nodeConfigurations', node.node_id, *path]))

    def connection(binding, kind):
        try:
            environment = environments.get(binding.environment_id)
            selected = next((c for c in environment.connections if c.connection_id == binding.connection_id), None)
            if selected is None or selected.kind != kind:
                raise Incompatible('请选择有效的' + ('模型' if kind == 'model' else 'API') + '连接')
            if selected.credential_ref:
                environments.credentials.get(selected.credential_ref)
        except (PlatformError, Incompatible) as exc:
            issue(str(exc), [kind])

    try:
        view = catalog.get(node.artifact_ref)
        if view.kind != node.kind:
            issue('节点类型与模块资源不符', ['artifactRef'])
        elif node.kind == 'block':
            if view.api_required:
                if not isinstance(config, BlockConfiguration):
                    issue('API 通用块须配置 API 连接和请求路径，不接受模型或预算配置', ['api'])
                else:
                    connection(config.api, 'api')
                    normalized = config.model_copy(deep=True)
            elif config is not None:
                issue('普通通用块无需节点连接配置，业务选项由上一层完整输出提供')
        elif not isinstance(config, NodeConfiguration):
            issue('业务包须配置模型连接、参数和预算，不接受 API 配置')
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
            connection(config.model, 'model')
    except PlatformError as exc:
        issue(str(exc), ['artifactRef'], exc.error.code)
    return NodeValidationResult(valid=not issues, issues=issues, configuration=normalized if not issues else None)


def validate_configurations(draft, catalog, environments):
    issues = []
    nodes = {node.node_id: node for node, _ in walk_nodes(draft.flow)}
    modules = {key: node for key, node in nodes.items() if isinstance(node, ModuleNode)}
    if any(node.kind == 'package' for node in modules.values()) and draft.budget is None:
        issues.append(ValidationIssue(code='CONFIGURATION_ERROR', reason='含业务包流程必须配置任务全局预算', field_path=['budget']))
    for key in draft.node_configurations.keys() - modules.keys():
        issues.append(ValidationIssue(code='CONFIGURATION_ERROR', reason='配置必须对应业务包或 API 通用块节点', node_id=key, field_path=['nodeConfigurations', key]))
    for node in modules.values():
        result = validate_node(NodeValidationRequest(node=node, configuration=draft.node_configurations.get(node.node_id)), catalog, environments)
        issues.extend(result.issues)
    return ValidationResult(valid=not issues, issues=issues)
