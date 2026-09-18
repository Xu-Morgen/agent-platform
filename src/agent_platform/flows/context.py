"""拼图包节点复用任务记录、模型适配和预算；能力从节点配置解析。"""
from ..runtime.context import RunContext
from ..blocks.api import BlockAPI
from ..runtime.validation import validate
from ..contracts.models import ModelRequest, ModelResponse


class FlowRunContext(RunContext):
    async def invoke_block(self, node_id, value):
        from ..contracts.flows import ModuleNode, walk_nodes
        from ..contracts.errors import PlatformError, ErrorResponse
        node = next((node for node, _ in walk_nodes(self.snapshot.draft.flow)
                     if node.node_id == node_id and isinstance(node, ModuleNode) and node.kind == 'block'), None)
        if node is None:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='block.binding',
                node_id=node_id, message='独立块节点不存在'))
        artifact = self.snapshot.catalog.artifact(node.artifact_ref)
        api = None
        if artifact.metadata.uses_api:
            binding = self.snapshot.draft.node_configurations[node_id].api
            api = BlockAPI(self.connection(binding), self.api_transport, path=binding.path)
        return await self.run_step('nodes.' + node_id,
            lambda: artifact.invoke(value, api=api), kind='block')

    async def call_model(self, node_id, value):
        binding = self.snapshot.draft.node_configurations[node_id].model
        async def execute():
            request = validate(ModelRequest, value, 'model.input')
            connection = self.connection(binding)
            adapter = self.model
            result = (await self.token_policy.invoke(node_id, adapter, connection, request)
                      if self.token_policy else await adapter.invoke(connection, request))
            return validate(ModelResponse, result, 'model.output')
        return await self.run_step('model.' + node_id, execute, kind='model', package_binding_id=node_id)
