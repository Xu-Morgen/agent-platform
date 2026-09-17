"""每次任务独立的实例上下文；图和能力使用固定内容。"""
from contextvars import ContextVar
from inspect import isawaitable
from .boundary import checkpoint
from ..contracts.runs import StepRecord
from ..contracts.errors import ErrorResponse, PlatformError

current_context = ContextVar('run_context', default=None)


def execution_error(exc, stage, run_id):
    if isinstance(exc, PlatformError):
        error = exc.error.model_copy(deep=True)
        error.run_id = run_id
        return error
    return ErrorResponse(code='INTERNAL_ERROR', stage=stage, message='步骤执行失败', run_id=run_id)


class RunContext:
    def __init__(self, run_id, snapshot, runs):
        self.run_id, self.snapshot, self.runs = run_id, snapshot, runs

    async def run_graph(self, value):
        return await self.snapshot.graph.run(value)

    async def run_step(self, step_id, operation, *, kind='step', package_binding_id=None):
        await checkpoint('step_start', step_id)
        steps = self.runs.get(self.run_id).steps
        attempt = 1 + sum(s.step_id == step_id and s.kind == kind for s in steps)
        step = StepRecord(run_id=self.run_id, step_id=step_id, kind=kind,
                          package_binding_id=package_binding_id, attempt=attempt)
        index = len(steps)
        steps.append(step)
        self.runs.update(self.run_id, steps=steps)
        try:
            value = operation()
            if isawaitable(value):
                value = await value
            await checkpoint('step_update', step_id)
            step.status = 'completed'
            return value
        except Exception as exc:
            step.status = 'failed'
            step.error = execution_error(exc, step_id, self.run_id)
            raise PlatformError(step.error) from None
        finally:
            steps = self.runs.get(self.run_id).steps
            steps[index] = step
            self.runs.update(self.run_id, steps=steps)

    def binding(self, binding_id, kind):
        key = tuple(binding_id.split('.', 1))
        binding = next((b for b in self.snapshot.definition.capability_bindings
                        if (b.package_binding_id, b.capability_id) == key and b.kind == kind), None)
        if binding is None:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage=kind + '.binding',
                                message='能力绑定不存在或类型不符', run_id=self.run_id))
        return key, binding

    async def call_block(self, binding_id, value):
        from .validation import validate
        key, binding = self.binding(binding_id, 'block')
        artifact = self.snapshot.blocks[key]
        manifest = artifact.manifest
        stage = 'blocks.' + binding_id

        async def execute():
            input_value = validate(artifact.content.load(manifest.input_model), value, stage + '.input')
            output = artifact.content.load(manifest.entry)(input_value)
            if isawaitable(output):
                output = await output
            return validate(artifact.content.load(manifest.output_model), output, stage + '.output')

        return await self.run_step(stage, execute, kind='block', package_binding_id=binding.package_binding_id)
