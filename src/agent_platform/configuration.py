"""配置组合应用服务：纯校验，不调用模型或业务入口。"""
from pydantic import ValidationError
from .contracts.instances import InstanceDefinition
from .contracts.packages import InstanceBudget
from .registry.validation import invalid, load_symbol, validation_error


def schema_shape(model):
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k not in ('title', 'description')}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return clean(model.model_json_schema())


def validate_environment_bindings(definition, environments):
    current = {key: environments.get(key) for key in definition.environment_refs}
    for i, binding in enumerate(definition.capability_bindings):
        if binding.kind == 'block':
            continue
        environment = current.get(binding.environment_id)
        connection = next((c for c in environment.connections if c.connection_id == binding.connection_id), None) if environment else None
        if connection is None or connection.kind != binding.kind:
            raise invalid('环境未引用或连接类型不满足能力要求', ['capabilityBindings', i, 'connectionId'])
        if connection.credential_ref:
            environments.credentials.get(connection.credential_ref)
    return current


def validate_combination(definition, content, packages, blocks, environments):
    try:
        definition = InstanceDefinition.model_validate(definition)
    except ValidationError as exc:
        raise validation_error(exc) from None
    validate_environment_bindings(definition, environments)
    artifacts = {b.binding_id: packages.get(b.package_id, b.version) for b in definition.package_bindings}
    scopes = {}
    for config in definition.config_refs:
        scopes.setdefault(config.scope, {}).update(config.values)
    budgets = []
    normalized_scopes = {}
    for binding_id, artifact in artifacts.items():
        scope = 'packages.' + binding_id
        model = load_symbol(artifact.content, artifact.manifest.contract_refs.configuration, ['configRefs', scope], model=True)
        values = {**artifact.manifest.budget_defaults.model_dump(by_alias=True), **scopes.get(scope, {})}
        try:
            config = model.model_validate(values)
        except ValidationError as exc:
            raise validation_error(exc, ['configRefs', scope, 'values']) from None
        normalized_scopes[scope] = config.model_dump(mode='json', by_alias=True)
        budgets.append(config)
    if 'instance' in scopes:
        if not definition.configuration_model:
            raise invalid('实例配置需要声明配置契约', ['configurationModel'])
        model = load_symbol(content, definition.configuration_model, ['configurationModel'], model=True)
        try:
            normalized_scopes['instance'] = model.model_validate(scopes['instance']).model_dump(mode='json', by_alias=True)
        except ValidationError as exc:
            raise validation_error(exc, ['configRefs', 'instance', 'values']) from None
    defaults = InstanceBudget(loop_limit=sum(c.loop_limit for c in budgets), token_limit=sum(c.token_limit for c in budgets))
    supplied = definition.budget.model_fields_set
    definition.budget = InstanceBudget(**{key: getattr(definition.budget if key in supplied else defaults, key) for key in InstanceBudget.model_fields})
    bindings = {}
    frozen_blocks = {}
    for i, binding in enumerate(definition.capability_bindings):
        key = (binding.package_binding_id, binding.capability_id)
        if key in bindings:
            raise invalid('能力绑定重复', ['capabilityBindings', i])
        bindings[key] = (i, binding)
    required = set()
    for binding_id, artifact in artifacts.items():
        for requirement in artifact.manifest.required_capabilities:
            key = (binding_id, requirement.capability_id)
            required.add(key)
            if key not in bindings:
                raise invalid('缺少包所需能力绑定', ['capabilityBindings', binding_id, requirement.capability_id], code='DEPENDENCY_ERROR')
            i, binding = bindings[key]
            if requirement.kind != binding.kind:
                raise invalid('能力类型不兼容', ['capabilityBindings', i, 'kind'])
            for direction in ('input_model', 'output_model'):
                expected = load_symbol(artifact.content, getattr(requirement, direction), ['requiredCapabilities'], model=True)
                declared = load_symbol(content, getattr(binding, direction), ['capabilityBindings', i, direction], model=True)
                if schema_shape(expected) != schema_shape(declared):
                    raise invalid('能力输入输出契约不兼容', ['capabilityBindings', i, direction])
                if binding.kind == 'block':
                    block = blocks.get(binding.block_id, binding.version)
                    actual = load_symbol(block.content, getattr(block.manifest, direction), ['block'], model=True)
                    if schema_shape(actual) != schema_shape(declared):
                        raise invalid('块契约不兼容', ['capabilityBindings', i, direction])
                    frozen_blocks[key] = block
    if set(bindings) != required:
        raise invalid('存在未声明的能力绑定', ['capabilityBindings'])
    return definition, artifacts, frozen_blocks, normalized_scopes, defaults
