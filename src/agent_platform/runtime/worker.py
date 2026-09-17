"""单 worker 消费固定快照，生命周期独立于提交连接。"""
import asyncio
from inspect import isawaitable
from .boundary import Boundary, current_boundary
from .context import RunContext, current_context, execution_error
from .validation import validate
from ..contracts.errors import ErrorResponse


class RunWorker:
    def __init__(self, submission, boundary_factory=Boundary):
        self.submission = submission
        self.boundary_factory = boundary_factory
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self.consume(), name='run-worker')

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def consume(self):
        while True:
            pending = await self.submission.queue.get()
            try:
                await self.execute(pending)
            finally:
                self.submission.queue.task_done()

    async def execute(self, pending):
        runs, envs = self.submission.runs, self.submission.environments
        run_id, snapshot = pending.run_id, pending.snapshot
        boundary = self.boundary_factory()
        context = RunContext(run_id, snapshot, runs)
        bt, ct = current_boundary.set(boundary), current_context.set(context)
        try:
            await boundary.check('run_start', run_id)
            runs.update(run_id, status='running')
            value = validate(snapshot.content.load(snapshot.definition.input_model), runs.get(run_id).input, 'runs.input')
            entry = snapshot.content.load(snapshot.definition.entry)
            result = await context.run_step('instance.entry', lambda: entry(value, context), kind='entry')
            result = validate(snapshot.content.load(snapshot.definition.output_model), result, 'runs.output')
            await boundary.check('terminal', run_id)
            with envs.lock:
                runs.finish(run_id, 'completed', result=result.model_dump(mode='json', by_alias=True))
        except asyncio.CancelledError:
            runs.finish(run_id, 'cancelled', error=ErrorResponse(code='APPLICATION_EXIT', stage='runtime', message='应用停止', run_id=run_id))
            raise
        except Exception as exc:
            runs.finish(run_id, 'failed', error=execution_error(exc, 'runtime', run_id))
        finally:
            try:
                await boundary.check('cleanup', run_id)
            finally:
                envs.release(run_id)
                current_context.reset(ct)
                current_boundary.reset(bt)
