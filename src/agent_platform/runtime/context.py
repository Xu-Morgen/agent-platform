"""拼图运行上下文的公共任务记录与包调用能力。"""
import asyncio
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
    from langgraph.errors import GraphRecursionError
    if isinstance(exc, GraphRecursionError):
        return ErrorResponse(code='GRAPH_EXECUTION_LIMIT', stage=stage, message='图执行步数超过限制', run_id=run_id)
    if isinstance(exc, ValidationError):
        return ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage=stage + '.output',
                             message='步骤数据不符合契约', run_id=run_id, field_path=list(exc.errors()[0]['loc']))
    return ErrorResponse(code='INTERNAL_ERROR', stage=stage, message='步骤执行失败', run_id=run_id)


class RunContext:
    def __init__(self, run_id, snapshot, runs, model=None, token_policy=None):
        self.run_id, self.snapshot, self.runs = run_id, snapshot, runs
        self.model = model
        self.token_policy = token_policy

    async def run_step(self, step_id, operation, *, kind='step', package_binding_id=None):
        await checkpoint('step_start', step_id)
        if kind == 'package':
            await checkpoint('package_start', package_binding_id)
        steps = self.runs.get(self.run_id).steps
        attempt = 1 + sum(s.step_id == step_id and s.kind == kind for s in steps)
        from ..flows.execution import execution_path
        step = StepRecord(execution_path=list(execution_path.get()), run_id=self.run_id, step_id=step_id, kind=kind,
                          package_binding_id=package_binding_id, attempt=attempt)
        index = len(steps)
        steps.append(step)
        self.runs.update(self.run_id, steps=steps)
        try:
            value = operation()
            if isawaitable(value):
                value = await value
            if kind == 'model':
                step.usage = value.usage.model_dump(mode='json', by_alias=True)
            await checkpoint('step_update', step_id)
            if kind in ('block', 'package'):
                from ..flows.execution import plain
                step.output = plain(value)
            step.status = 'completed'
            return value
        except asyncio.CancelledError:
            step.status = 'failed'
            step.error = ErrorResponse(code='APPLICATION_EXIT', stage=step_id, message='应用停止', run_id=self.run_id)
            raise
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

    def connection(self, binding):
        environments = self.runs.get(self.run_id).environment_snapshot
        environment = next(e for e in environments if e.environment_id == binding.environment_id)
        return next(c for c in environment.connections if c.connection_id == binding.connection_id)

    async def invoke_package(self, binding_id, value):
        from .packages import invoke_prompt
        artifact = self.snapshot.packages.get(binding_id)
        if artifact is None:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='packages.binding', message='包绑定不存在'))
        return await self.run_step('packages.' + binding_id,
            lambda: invoke_prompt(self, binding_id, artifact, value), kind='package', package_binding_id=binding_id)
