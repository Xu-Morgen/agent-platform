"""任务固定模型与受控 OCR 调用；原图不写入历史。"""
import asyncio
import base64
from hashlib import sha256
from pydantic import ValidationError
from ..contracts.ocr import OCRRequest, OCRResult, OCRRecord
from ..runtime.boundary import checkpoint
from .adapter import failure


class TaskOCR:
    def __init__(self, repository, runs, run_id):
        self.repository, self.runs, self.run_id = repository, runs, run_id
        self.session = None
        self.calls = 0
        self.lock = asyncio.Lock()

    async def invoke(self, payload, node_id, resource_digest):
        async with self.lock:
            return await self._invoke(payload, node_id, resource_digest)

    async def _invoke(self, payload, node_id, resource_digest):
        await checkpoint('ocr_access', node_id)
        run = self.runs.get(self.run_id)
        if run.status != 'running' or run.cancel_requested:
            raise failure('RUN_CANCELLED', '任务已结束或取消，不再接受 OCR')
        if run.ocr_snapshot is None:
            raise failure('OCR_NOT_SELECTED', '任务未固定 OCR 模型')
        try:
            request = OCRRequest.model_validate(payload)
            data = base64.b64decode(request.image_base64, validate=True)
        except (ValidationError, ValueError):
            raise failure('OCR_INPUT_LIMIT', 'OCR 请求不符合图片输入契约') from None
        self.calls += 1
        if self.calls > 200:
            raise failure('OCR_INPUT_LIMIT', '单任务最多 200 次 OCR 调用')
        snapshot = run.ocr_snapshot
        self.session = self.repository.processes.session(self.repository.root / snapshot.model_id, snapshot)
        session = self.session
        pending = asyncio.create_task(session.call('recognize', request=request.model_dump(mode='json', by_alias=True)))
        try:
            while not pending.done():
                await asyncio.wait({pending}, timeout=.05)
                await checkpoint('ocr_wait', node_id)
            payload = await pending
            try:
                result = OCRResult.model_validate(payload)
            except ValidationError:
                raise failure('OCR_INFERENCE_ERROR', 'OCR 返回框、文字或统计不符合契约') from None
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            queue_seconds = session.queue_seconds
            # OCR 无任务向量缓存；每次调用结束释放容量，避免与 embedding 交叉等待。
            await self.close()
        await checkpoint('ocr_result', node_id)
        if result.model_id != run.ocr_snapshot.model_id or result.image_sha256 != sha256(data).hexdigest():
            raise failure('OCR_INFERENCE_ERROR', 'OCR 响应模型或图片身份无效')
        result.queue_seconds = queue_seconds
        self.runs.append_ocr(self.run_id, OCRRecord(node_id=node_id, resource_digest=resource_digest,
            use_classification=request.use_classification, result=result))
        return result.model_dump(mode='json', by_alias=True)

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None
