from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.flows.configuration import NodeValidationRequest, validate_node, validate_configurations
from agent_platform.contracts.flows import FlowDraft
from flow_ports import fixture

app = create_app()
catalog, envs = app.state.catalog, app.state.environments
package = catalog.load(CatalogLoad(kind='package', path='examples/execution/model-package'))
environments = [envs.save(EnvironmentWrite(name=name, connections=[{'connectionId': 'model', 'kind': 'model', 'baseUrl': 'http://localhost:11434', 'model': 'synthetic'}])) for name in ('one', 'two')]
results = []
for index, environment in enumerate(environments):
    request = NodeValidationRequest.model_validate({'node': {'nodeId': f'node{index}', 'kind': 'package', 'artifactRef': package.resource_id},
        'configuration': {'parameters': {'maxOutputTokens': 64 + index}, 'budget': {'loopLimit': index+1, 'tokenLimit': 100}, 'capabilities': {
            'llm': {'kind': 'model', 'environmentId': environment.environment_id, 'connectionId': 'model'}}}, 'strictTokenLimit': False})
    # 示例使用自己的能力标识。
    key = catalog.artifact(package.resource_id).manifest.required_capabilities[0].capability_id
    request.configuration.capabilities[key] = request.configuration.capabilities.pop('llm')
    result = validate_node(request, catalog, envs)
    assert result.valid, result
    results.append(result)
    request.strict_token_limit = True
    assert validate_node(request, catalog, envs).issues[0].code == 'TOKEN_ACCOUNTING_UNSUPPORTED'
    request.strict_token_limit = False
    request.configuration.capabilities[key].connection_id = 'missing'
    assert not validate_node(request, catalog, envs).valid
    request.configuration = None
    assert not validate_node(request, catalog, envs).valid
assert results[0].configuration.parameters != results[1].configuration.parameters
assert results[0].configuration.budget.loop_limit != results[1].configuration.budget.loop_limit
catalog, draft = fixture()
assert validate_configurations(FlowDraft.model_validate(draft), catalog, envs).valid
print('flow configuration: OK (同包独立预算/环境、缺配置/错误连接拒绝、严格模式不降级、纯块通过)')
