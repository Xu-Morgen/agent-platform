"""包仅可访问声明的能力，不暴露包调度或任务状态写入入口。"""
from .boundary import checkpoint
from ..contracts.errors import ErrorResponse, PlatformError


class PackageContext:
    __slots__ = ('_runtime', '_binding_id', '_artifact')

    def __init__(self, runtime, binding_id, artifact):
        self._runtime, self._binding_id, self._artifact = runtime, binding_id, artifact

    async def call_capability(self, capability_id, value):
        requirement = next((r for r in self._artifact.manifest.required_capabilities if r.capability_id == capability_id), None)
        if requirement is None:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='packages.capability', message='包未声明此能力'))
        binding_id = self._binding_id + '.' + capability_id
        if requirement.kind == 'block':
            return await self._runtime.call_block(binding_id, value)
        if requirement.kind == 'api':
            return await self._runtime.call_api(binding_id, value)
        return await self._runtime._call_model(binding_id, value)

    async def call_model(self, capability_id, request):
        requirement = next((r for r in self._artifact.manifest.required_capabilities if r.capability_id == capability_id), None)
        if requirement is None or requirement.kind != 'model':
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='packages.model', message='包未声明此模型能力'))
        return await self.call_capability(capability_id, request)

    def read_resource(self, name):
        return self._artifact.content.read_resource(name)

    async def record_progress(self, step_id, message):
        # 只发布检查事件；不保存任意业务文本或凭据。
        await checkpoint('progress', self._binding_id + '.' + step_id)
