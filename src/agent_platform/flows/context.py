"""拼图包节点复用任务记录、模型适配和预算；能力从节点配置解析。"""
from types import SimpleNamespace
from ..runtime.context import RunContext
from ..runtime.validation import validate


class FlowRunContext(RunContext):
    async def invoke_block(self, node_id, value):
        from ..contracts.flows import ModuleNode, walk_nodes
        from ..contracts.errors import PlatformError, ErrorResponse
        node = next((node for node, _ in walk_nodes(self.snapshot.draft.flow)
                     if node.node_id == node_id and isinstance(node, ModuleNode) and node.kind == 'block'), None)
        if node is None:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='block.binding',
                node_id=node_id, message='独立块节点不存在'))
        return await self.run_step('nodes.' + node_id,
            lambda: self.snapshot.catalog.artifact(node.artifact_ref).invoke(value), kind='block')

    def binding(self, binding_id, kind):
        node_id, capability_id = binding_id.split('.', 1)
        selection = self.snapshot.draft.node_configurations[node_id].capabilities[capability_id]
        if selection.kind != kind:
            raise ValueError('能力类型不符')
        return (node_id, capability_id), SimpleNamespace(**selection.model_dump(), package_binding_id=node_id)

    def requirement(self, binding_id):
        node_id, capability_id = binding_id.split('.', 1)
        artifact = self.snapshot.packages[node_id]
        requirement = next(r for r in artifact.manifest.required_capabilities if r.capability_id == capability_id)
        return artifact, requirement

    async def call_block(self, binding_id, value):
        _, binding = self.binding(binding_id, 'block')
        artifact, requirement = self.requirement(binding_id)
        async def execute():
            parsed = validate(artifact.content.load(requirement.input_model), value, 'block.input')
            result = await self.snapshot.catalog.artifact(binding.artifact_ref).invoke(parsed.model_dump(by_alias=True))
            return validate(artifact.content.load(requirement.output_model), result, 'block.output')
        return await self.run_step('blocks.' + binding_id, execute, kind='block', package_binding_id=binding.package_binding_id)

    async def call_api(self, binding_id, value):
        _, binding = self.binding(binding_id, 'api')
        artifact, requirement = self.requirement(binding_id)
        async def execute():
            parsed = validate(artifact.content.load(requirement.input_model), value, 'api.input')
            result = await self.api.call(self.connection(binding), binding, parsed)
            return validate(artifact.content.load(requirement.output_model), result, 'api.output')
        return await self.run_step('api.' + binding_id, execute, kind='api', package_binding_id=binding.package_binding_id)

    async def _call_model(self, binding_id, value):
        _, binding = self.binding(binding_id, 'model')
        artifact, requirement = self.requirement(binding_id)
        async def execute():
            request = validate(artifact.content.load(requirement.input_model), value, 'model.input')
            connection = self.connection(binding)
            adapter = self.model.for_connection(connection) if hasattr(self.model, 'for_connection') else self.model
            result = (await self.token_policy.invoke(binding.package_binding_id, adapter, connection, request)
                      if self.token_policy else await adapter.invoke(connection, request))
            return validate(artifact.content.load(requirement.output_model), result, 'model.output')
        return await self.run_step('model.' + binding_id, execute, kind='model', package_binding_id=binding.package_binding_id)
