"""nodeId 独立配置校验；只读取环境，不占用环境或调用能力。"""
from pydantic import ValidationError
from ..contracts.flows import ModuleNode, NodeConfiguration, walk_nodes
from ..contracts.base import StrictModel
from ..contracts.errors import PlatformError
from ..contracts.models import ModelRequest, ModelResponse
from ..registry.validation import schema_shape
from .validation import ValidationIssue, ValidationResult
from .compatibility import assignable, Incompatible


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
            model = artifact.content.load(artifact.manifest.contract_refs.configuration)
            if {'loopLimit', 'tokenLimit', 'loop_limit', 'token_limit'} & config.parameters.keys():
                issue('预算只能在 budget 声明，不能与 parameters 重复', ['parameters'])
            try:
                value = model.model_validate({**config.parameters, **config.budget.model_dump(by_alias=True)}, strict=True)
                parameters = value.model_dump(mode='json', by_alias=True)
                for key in ('loopLimit', 'tokenLimit'):
                    parameters.pop(key, None)
                normalized = config.model_copy(update={'parameters': parameters}, deep=True)
            except ValidationError as exc:
                from ..validation_issues import issues_from_errors
                issues.extend(issues_from_errors(exc.errors(), stage='node.configuration',
                    prefix=['nodeConfigurations', node.node_id, 'parameters'], node_id=node.node_id, code='CONFIGURATION_ERROR'))
            requirements = {r.capability_id: r for r in artifact.manifest.required_capabilities}
            for extra in config.capabilities.keys() - requirements.keys():
                issue('存在包未声明的能力', ['capabilities', extra])
            for key, requirement in requirements.items():
                selection = config.capabilities.get(key)
                path = ['capabilities', key]
                if selection is None:
                    issue('缺少所需能力绑定', path)
                    continue
                if selection.kind != requirement.kind:
                    issue('能力绑定类型不满足包要求', path + ['kind'])
                    continue
                try:
                    if selection.kind == 'block':
                        if not selection.artifact_ref or selection.environment_id or selection.connection_id or selection.api_method or selection.api_path:
                            raise Incompatible('块能力必须仅绑定块资源')
                        block = catalog.get(selection.artifact_ref)
                        if block.kind != 'block':
                            raise Incompatible('绑定资源不是通用块')
                        required_input = artifact.content.load(requirement.input_model)
                        required_output = artifact.content.load(requirement.output_model)
                        assignable(required_input.model_json_schema(), block.schemas['input'])
                        assignable(block.schemas['output'], required_output.model_json_schema())
                    else:
                        if not selection.environment_id or not selection.connection_id or selection.artifact_ref:
                            raise Incompatible('能力必须选择环境及连接，不得混用块资源')
                        environment = environments.get(selection.environment_id)
                        connection = next((c for c in environment.connections if c.connection_id == selection.connection_id), None)
                        if connection is None or connection.kind != selection.kind:
                            raise Incompatible('连接不存在或连接类型不满足能力要求')
                        if connection.credential_ref:
                            environments.credentials.get(connection.credential_ref)
                        if selection.kind == 'model':
                            if selection.api_method or selection.api_path:
                                raise Incompatible('模型能力不声明 API 方法或路径')
                            for reference, expected in [(requirement.input_model, ModelRequest), (requirement.output_model, ModelResponse)]:
                                if schema_shape(artifact.content.load(reference)) != schema_shape(expected):
                                    raise Incompatible('模型能力必须使用平台请求/响应契约')
                            if request.strict_token_limit:
                                # 当前两种已安装适配器均不能保证完整输入及隐藏 token 上界。
                                issue('所选模型适配器不能保证严格 token 上限，请明确选择非严格模式或支持该能力的适配器', path, 'TOKEN_ACCOUNTING_UNSUPPORTED')
                        elif not selection.api_method or (selection.api_path and (not selection.api_path.startswith('/') or selection.api_path.startswith('//') or '?' in selection.api_path or '#' in selection.api_path)):
                            raise Incompatible('API 能力必须选择方法及规范相对路径')
                except (PlatformError, Incompatible) as exc:
                    issue(str(exc), path)
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
