"""单 worker 消费固定快照，生命周期独立于提交连接。"""
import asyncio
from ..adapters.openai_chat import OpenAIChatAdapter
from ..adapters.http import JsonTransport
from .boundary import Boundary, current_boundary
from .cancellation import CancellationPolicy, terminal_for_error
from .budgets import LoopPolicy, TokenPolicy
from .context import current_context, execution_error
from ..flows.context import FlowRunContext
from ..contracts.errors import ErrorResponse
from ..contracts.runs import TERMINAL


class RunWorker:
    def __init__(self, submission, boundary_factory=Boundary):
        self.submission = submission
        self.boundary_factory = boundary_factory
        self.task = None
        self.stop_lock = asyncio.Lock()

    def start(self):
        self.task = asyncio.create_task(self.consume(), name='run-worker')

    async def stop(self):
        async with self.stop_lock:
            self.submission.stopping = True
            if self.task:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
                self.task = None
            while not self.submission.queue.empty():
                pending = self.submission.queue.get_nowait()
                try:
                    if self.submission.runs.get(pending.run_id).status not in TERMINAL:
                        self.submission.runs.finish(pending.run_id, 'cancelled', error=ErrorResponse(
                            code='APPLICATION_EXIT', stage='runtime', message='应用停止', run_id=pending.run_id))
                    self.submission.environments.release(pending.run_id)
                finally:
                    self.submission.queue.task_done()

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
        if runs.get(run_id).status in TERMINAL:
            return
        boundary = self.boundary_factory()
        model = OpenAIChatAdapter(envs.credentials)
        api_transport = JsonTransport(envs.credentials)
        token_policy = None
        policies = (CancellationPolicy(runs, run_id),) + boundary.policies
        if snapshot.packages:
            token_policy = TokenPolicy(run_id, snapshot, runs)
            policies += (token_policy, LoopPolicy(run_id, snapshot, runs))
        boundary.policies = policies
        context = FlowRunContext(run_id, snapshot, runs, model, token_policy, api_transport)
        context.files = self.submission.files
        bt, ct = current_boundary.set(boundary), current_context.set(context)
        try:
            await boundary.check('run_start', run_id)
            with envs.lock, runs.lock:
                if runs.get(run_id).status in TERMINAL:
                    return
                runs.update(run_id, status='running')
            result = await snapshot.graph.run(runs.get(run_id).input)
            await boundary.check('terminal', run_id)
            with envs.lock, runs.lock:
                if runs.get(run_id).cancel_requested:
                    runs.finish(run_id, 'cancelled')
                else:
                    runs.finish(run_id, 'completed', result=result)
        except asyncio.CancelledError:
            if runs.get(run_id).status not in TERMINAL:
                runs.finish(run_id, 'cancelled', error=ErrorResponse(code='APPLICATION_EXIT', stage='runtime', message='应用停止', run_id=run_id))
            raise
        except Exception as exc:
            error = execution_error(exc, 'runtime', run_id)
            runs.finish(run_id, terminal_for_error(error), error=error)
        finally:
            try:
                await boundary.check('cleanup', run_id)
            finally:
                await asyncio.gather(model.close(), api_transport.close())
                envs.release(run_id)
                current_context.reset(ct)
                current_boundary.reset(bt)
