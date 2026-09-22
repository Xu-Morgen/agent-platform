"""平台注入的文件及模型访问接口；业务契约不携带运行路径。"""
from types import MappingProxyType
from ..contracts.files import FileReference
from ..contracts.errors import ErrorResponse, PlatformError


class BlockContext:
    def __init__(self, *, files=None, run_id=None, models=None, progress=None, knowledge=None, semantic=None):
        self._files, self._run_id = files, run_id
        self._knowledge = knowledge
        self._semantic = semantic
        self._models = MappingProxyType(dict(models or {}))
        self._progress = progress or (lambda event: None)

    def progress(self, message, *, current=None, total=None):
        self._progress({'message': str(message), 'current': current, 'total': total})

    def file(self, reference: FileReference):
        if self._files is None or self._run_id is None:
            raise PlatformError(ErrorResponse(code='FILE_NOT_FOUND', stage='block.context', message='任务文件上下文不可用'))
        return self._files.resolve(reference, run_id=self._run_id)

    def model(self, name: str):
        if name not in self._models:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='block.context', message='声明的模型文件未就绪'))
        return self._models[name]

    async def knowledge_resolve(self, reference):
        from ..contracts.knowledge import KnowledgeReference, FixedKnowledgeReference
        return FixedKnowledgeReference.model_validate(await self._knowledge_call('resolve', KnowledgeReference.model_validate(reference)))

    async def knowledge_list(self, request):
        from ..contracts.knowledge import KnowledgePageRequest, KnowledgePage
        return KnowledgePage.model_validate(await self._knowledge_call('list', KnowledgePageRequest.model_validate(request)))

    async def knowledge_metadata(self, request):
        from ..contracts.knowledge import DocumentReadRequest, DocumentVersion
        return DocumentVersion.model_validate(await self._knowledge_call('metadata', DocumentReadRequest.model_validate(request)))

    async def knowledge_file(self, request):
        from pathlib import Path
        from ..contracts.knowledge import DocumentReadRequest
        return Path(await self._knowledge_call('file', DocumentReadRequest.model_validate(request)))

    async def knowledge_record(self, evidence):
        from ..contracts.knowledge import EvidenceRegistration, EvidenceRecord
        request = EvidenceRegistration.model_validate(evidence)
        return EvidenceRecord.model_validate(await self._knowledge_call('record', request))

    async def _knowledge_call(self, operation, request):
        if self._knowledge is None:
            raise PlatformError(ErrorResponse(code='KNOWLEDGE_SCOPE_ERROR', stage='block.context', message='当前任务未绑定知识库访问能力'))
        return await self._knowledge(operation, request.model_dump(mode='json', by_alias=True))

    async def semantic_search(self, request):
        from ..contracts.embedding import SemanticSearchRequest, SemanticSearchResult
        return SemanticSearchResult.model_validate(await self._semantic_call('search', SemanticSearchRequest.model_validate(request)))

    async def semantic_split(self, request):
        from ..contracts.embedding import SemanticSearchRequest
        return SemanticSearchRequest.model_validate(await self._semantic_call('split_corpus', SemanticSearchRequest.model_validate(request)))

    async def _semantic_call(self, operation, request):
        if self._semantic is None:
            raise PlatformError(ErrorResponse(code='EMBEDDING_NOT_READY', stage='block.context', message='语义检索上下文不可用'))
        return await self._semantic(operation, request.model_dump(mode='json', by_alias=True))
