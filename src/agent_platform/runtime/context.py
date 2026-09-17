"""每次任务独立的实例上下文；图和能力使用固定内容。"""
from contextvars import ContextVar
from inspect import isawaitable
from pydantic import ValidationError
from .boundary import checkpoint
from ..contracts.runs import StepRecord
from ..contracts.errors import ErrorResponse, PlatformError

current_context = ContextVar('run_context', default=None)


def execution_error(exc, stage, run_id):
    if isinstance(exc, PlatformError):
        error = exc.error.model_copy(deep=True)
        error.run_id = run_id
        return error
    if isinstance(exc, ValidationError):
        return ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage=stage + '.output',
                             message='步骤数据不符合契约', run_id=run_id, field_path=list(exc.errors()[0]['loc']))
    return ErrorResponse(code='INTERNAL_ERROR', stage=stage, message='步骤执行失败', run_id=run_id)


class RunContext:
    def __init__(self, run_id, snapshot, runs, api=None, model=None):
        self.run_id, self.snapshot, self.runs = run_id, snapshot, runs
        self.api = api
        self.model = model

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
            if kind == 'model':
                step.usage = value.usage.model_dump(mode='json', by_alias=True)
            step.status = 'completed'
            return value
        except Exception as exc:
            step.status = 'failed'
            step.error = execution_error(exc, step_id, self.run_id)
            if getattr(exc, 'usage', None) is not None:
                step.usage = exc.usage.model_dump(mode='json', by_alias=True)
            if kind == 'package':
                step.error.details.package_binding_id = package_binding_id
                step.error.details.attempt = attempt
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

    def connection(self, binding):
        environments = self.runs.get(self.run_id).environment_snapshot
        environment = next(e for e in environments if e.environment_id == binding.environment_id)
        return next(c for c in environment.connections if c.connection_id == binding.connection_id)

    async def call_api(self, binding_id, value):
        from .validation import validate
        _, binding = self.binding(binding_id, 'api')
        stage = 'api.' + binding_id

        async def execute():
            input_value = validate(self.snapshot.content.load(binding.input_model), value, stage + '.input')
            result = await self.api.call(self.connection(binding), binding, input_value)
            return validate(self.snapshot.content.load(binding.output_model), result, stage + '.output')

        return await self.run_step(stage, execute, kind='api', package_binding_id=binding.package_binding_id)

    async def invoke_package(self, binding_id, value):
        from .validation import validate
        from .packages import PackageContext
        artifact = self.snapshot.packages.get(binding_id)
        if artifact is None:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='packages.binding', message='包绑定不存在'))
        stage = 'packages.' + binding_id
        await checkpoint('package_start', binding_id)

        async def execute():
            manifest = artifact.manifest
            input_value = validate(artifact.content.load(manifest.contract_refs.input), value, stage + '.input')
            config = validate(artifact.content.load(manifest.contract_refs.configuration),
                              self.snapshot.configuration['packages.' + binding_id], stage + '.configuration')
            result = artifact.content.load(manifest.entry)(input_value, config, PackageContext(self, binding_id, artifact))
            if isawaitable(result):
                result = await result
            return validate(artifact.content.load(manifest.contract_refs.output), result, stage + '.output')

        return await self.run_step(stage, execute, kind='package', package_binding_id=binding_id)

    async def _call_model(self, binding_id, value):
        from .validation import validate
        _, binding = self.binding(binding_id, 'model')
        stage = 'model.' + binding_id

        async def execute():
            request = validate(self.snapshot.content.load(binding.input_model), value, stage + '.input')
            result = await self.model.invoke(self.connection(binding), request)
            return validate(self.snapshot.content.load(binding.output_model), result, stage + '.output')

        return await self.run_step(stage, execute, kind='model', package_binding_id=binding.package_binding_id)
