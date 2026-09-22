"""父进程校验声明、任务绑定和版本范围，再调用任务独占模型进程。"""
import asyncio
from pydantic import ValidationError
from ..contracts.embedding import SemanticSearchRequest, SemanticSearchResult, SemanticSearchRecord
from ..contracts.knowledge import DocumentReadRequest
from ..runtime.boundary import checkpoint
from .adapter import failure


class TaskEmbedding:
    def __init__(self, repository, runs, run_id):
        self.repository, self.runs, self.run_id = repository, runs, run_id
        self.session = None
        self.calls = 0

    async def invoke(self, operation, payload, access):
        await checkpoint('embedding_access', access.node_id)
        run = self.runs.get(self.run_id)
        if run.status != 'running' or run.cancel_requested:
            raise failure('RUN_CANCELLED', '任务已终止或取消，不再接受语义检索')
        if run.embedding_snapshot is None:
            raise failure('EMBEDDING_NOT_SELECTED', '任务未固定语义检索模型')
        try:
            request = SemanticSearchRequest.model_validate(payload)
        except ValidationError:
            raise failure('EMBEDDING_INPUT_LIMIT', '语义检索请求的片段、摘要、范围或数量不符合契约') from None
        access.resolve(request.reference)
        if access.repository is None:
            raise failure('KNOWLEDGE_SCOPE_ERROR', '当前任务未绑定知识库')
        for item in request.fragments:
            metadata = access.repository.metadata(DocumentReadRequest(reference=request.reference, version_id=item.version_id))
            if item.document_id != metadata.document_id:
                raise failure('KNOWLEDGE_SCOPE_ERROR', '片段文档身份与任务固定版本不一致')
        if operation not in ('search', 'split_corpus'):
            raise failure('EMBEDDING_INCOMPATIBLE', '未知语义检索能力')
        self.calls += 1
        if self.calls > 200:
            raise failure('EMBEDDING_INPUT_LIMIT', '单任务最多 200 次语义检索/切分请求')
        if self.session is None:
            snapshot = run.embedding_snapshot
            self.session = self.repository.processes.session(self.repository.root / snapshot.model_id, snapshot)
        pending = asyncio.create_task(self.session.call(operation, request=request.model_dump(mode='json', by_alias=True)))
        try:
            while not pending.done():
                await asyncio.wait({pending}, timeout=.05)
                await checkpoint('embedding_wait', access.node_id)
            result = await pending
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        await checkpoint('embedding_result', access.node_id)
        if operation == 'split_corpus':
            result = SemanticSearchRequest.model_validate(result)
            # 工作进程返回的是带原文定位的片段，模型与范围不可由调用者切换。
            if result.reference != request.reference or result.query != request.query:
                raise failure('EMBEDDING_INFERENCE_ERROR', '切分响应改变了请求范围')
            return result.model_dump(mode='json', by_alias=True)
        result = SemanticSearchResult.model_validate(result)
        if (result.model != run.embedding_snapshot or result.reference != request.reference
                or result.splitter != request.splitter or result.scope_limited != request.scope_limited
                or len(result.candidates) > request.top_k):
            raise failure('EMBEDDING_INFERENCE_ERROR', '语义检索响应身份或范围无效')
        originals = {item.fragment_id: item for item in request.fragments}
        for item in result.candidates:
            original = originals.get(item.fragment_id)
            if (original is None or item.model_copy(update={'score': original.score}) != original
                    or request.minimum_score is not None and item.score < request.minimum_score):
                raise failure('EMBEDDING_INFERENCE_ERROR', '语义检索候选不属于请求或不满足阈值')
        result.stats.queue_seconds = self.session.queue_seconds
        self.session.queue_seconds = 0.0
        record = SemanticSearchRecord(node_id=access.node_id, resource_digest=access.resource_digest,
            query=request.query, top_k=request.top_k, minimum_score=request.minimum_score, result=result)
        self.runs.append_semantic_search(self.run_id, record)
        return result.model_dump(mode='json', by_alias=True)

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None
