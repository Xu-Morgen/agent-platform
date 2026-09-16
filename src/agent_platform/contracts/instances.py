"""实例组合声明；不分配版本、不保存快照。"""
from typing import Annotated, Literal
from pydantic import Field, JsonValue, ValidationError, model_validator
from .base import StrictModel
from .packages import Identifier, SymbolReference, Version, InstanceBudget


class PackageBinding(StrictModel):
    binding_id: Identifier
    package_id: Identifier
    version: Version


class ConfigurationReference(StrictModel):
    config_id: Identifier
    revision: Annotated[int, Field(gt=0)]
    scope: str = Field(pattern=r'^(?:instance|packages\.[A-Za-z][A-Za-z0-9_-]*)$')
    values: dict[str, JsonValue]


class CapabilityBinding(StrictModel):
    package_binding_id: Identifier
    capability_id: Identifier
    kind: Literal['model', 'api', 'block']
    environment_id: Identifier | None = None
    connection_id: Identifier | None = None
    block_id: Identifier | None = None
    version: Version | None = None
    input_model: SymbolReference
    output_model: SymbolReference

    @model_validator(mode='after')
    def target(self):
        if self.kind == 'block':
            valid = self.block_id and self.version and not self.environment_id and not self.connection_id
        else:
            valid = self.environment_id and self.connection_id and not self.block_id and not self.version
        if not valid:
            raise ValueError('能力绑定目标不完整或混合了不同类型')
        return self


class InstanceDefinition(StrictModel):
    definition_id: Identifier
    entry: SymbolReference
    workflow: SymbolReference
    input_model: SymbolReference
    output_model: SymbolReference
    package_bindings: list[PackageBinding] = Field(min_length=1)
    config_refs: list[ConfigurationReference] = Field(min_length=1)
    environment_refs: list[Identifier]
    budget: InstanceBudget
    capability_bindings: list[CapabilityBinding] = Field(default_factory=list)
    configuration_model: SymbolReference | None = None

    @model_validator(mode='after')
    def validate_bindings(self):
        errors = []

        def error(loc, reason):
            errors.append({'type': 'value_error', 'loc': loc, 'ctx': {'error': ValueError(reason)}})

        bindings = set()
        for i, binding in enumerate(self.package_bindings):
            if binding.binding_id in bindings:
                error(('packageBindings', i, 'bindingId'), '包绑定标识重复')
            bindings.add(binding.binding_id)
        ids, fields = set(), set()
        for i, config in enumerate(self.config_refs):
            if config.config_id in ids:
                error(('configRefs', i, 'configId'), '配置标识重复')
            ids.add(config.config_id)
            if config.scope != 'instance' and config.scope.removeprefix('packages.') not in bindings:
                error(('configRefs', i, 'scope'), '配置引用了不存在的包绑定')
            for key in config.values:
                scoped = (config.scope, key)
                if scoped in fields:
                    error(('configRefs', i, 'values', key), '同作用域字段重复定义')
                fields.add(scoped)
        if len(set(self.environment_refs)) != len(self.environment_refs):
            error(('environmentRefs',), '环境引用重复')
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self
