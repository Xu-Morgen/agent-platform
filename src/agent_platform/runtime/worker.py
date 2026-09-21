"""单后端内的有限并发消费者池；每次执行独立持有任务上下文。"""
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
    def __init__(self, submission, boundary_factory=Boundary, *, concurrency=None):
        self.submission = submission
        self.boundary_factory = boundary_factory
        from ..contracts.settings import PlatformSettings
        settings = PlatformSettings() if concurrency is None else PlatformSettings(run_concurrency=concurrency)
        self.concurrency = settings.run_concurrency
        self.tasks = []
        self.stop_lock = asyncio.Lock()

    @property
    def healthy(self):
        return (not self.submission.stopping and len(self.tasks) == self.concurrency
                and all(not task.done() for task in self.tasks))

    def start(self):
        if self.tasks or self.submission.stopping:
            raise RuntimeError('任务执行器不能重复启动或在停止后重启')
        self.tasks = [asyncio.create_task(self.consume(), name=f'run-worker-{index + 1}')
                      for index in range(self.concurrency)]

    async def stop(self):
        async with self.stop_lock:
            self.submission.stopping = True
            # 先同时取消全部消费者，再等待传输和上下文清理，最后处理排队任务。
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.tasks.clear()
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
        if snapshot.all_packages:
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
                try:
                    await asyncio.gather(model.close(), api_transport.close())
                finally:
                    envs.release(run_id)
                    current_context.reset(ct)
                    current_boundary.reset(bt)
