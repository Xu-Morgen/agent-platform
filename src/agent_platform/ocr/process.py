"""有容量与超时约束的模型进程，任务结束统一释放。"""
import asyncio
import json
import os
from pathlib import Path
import sys
from time import perf_counter

from ..contracts.errors import ErrorResponse, PlatformError
from .adapter import failure


class OCRProcesses:
    def __init__(self):
        self.capacity = asyncio.Semaphore(1)
        self.sessions = set()
        self.closed = False

    def session(self, root, snapshot):
        if self.closed:
            raise failure('OCR_NOT_READY', '模型进程管理器已关闭')
        value = Session(self, root, snapshot)
        self.sessions.add(value)
        return value

    async def close(self):
        self.closed = True
        await asyncio.gather(*(session.close() for session in list(self.sessions)))


class Session:
    def __init__(self, owner, root, snapshot):
        self.owner, self.root, self.snapshot = owner, root, snapshot
        self.process = None
        self.acquired = False
        self.closed = False
        self.queue_seconds = 0.0
        self.lock = asyncio.Lock()

    async def start(self):
        started = perf_counter()
        try:
            await asyncio.wait_for(self.owner.capacity.acquire(), 120)
        except TimeoutError:
            raise failure('OCR_CAPACITY_EXCEEDED', '本地模型工作进程已占用，等待超过 120 秒') from None
        self.acquired = True
        self.queue_seconds = perf_counter() - started
        if self.closed or self.owner.closed:
            await self.close()
            raise failure('OCR_NOT_READY', '本地模型会话已关闭')
        allowed = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR'}
        env = {key: value for key, value in os.environ.items() if key in allowed}
        env.update(PYTHONPATH=str(Path(__file__).resolve().parents[2]), PYTHONNOUSERSITE='1',
                   PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='1',
                   TOKENIZERS_PARALLELISM='false')
        self.process = await asyncio.create_subprocess_exec(sys.executable, '-B', '-m', 'agent_platform.ocr.worker',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=env, limit=16 * 1024 * 1024)
        await self.exchange({'root': str(self.root), 'snapshot': self.snapshot.model_dump(mode='json', by_alias=True)})

    async def exchange(self, message):
        try:
            async with asyncio.timeout(120):
                self.process.stdin.write((json.dumps(message, ensure_ascii=False) + '\n').encode())
                await self.process.stdin.drain()
                line = await self.process.stdout.readline()
                if not line:
                    raise ValueError()
                result = json.loads(line)
                if 'error' in result:
                    raise PlatformError(ErrorResponse.model_validate(result['error']))
                return result['value']
        except PlatformError:
            raise
        except (TimeoutError, ValueError, OSError, KeyError):
            raise failure('OCR_INFERENCE_ERROR', '本地模型工作进程退出、超时或响应无效') from None

    async def call(self, operation, **values):
        async with self.lock:
            if self.closed:
                raise failure('OCR_NOT_READY', '任务模型上下文已清理')
            try:
                if self.process is None:
                    await self.start()
                return await self.exchange({'operation': operation, **values})
            except BaseException:
                await self.close()
                raise

    async def close(self):
        self.closed = True
        if self.process is not None:
            process, self.process = self.process, None
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 2)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        if self.acquired:
            self.acquired = False
            self.owner.capacity.release()
        self.owner.sessions.discard(self)
