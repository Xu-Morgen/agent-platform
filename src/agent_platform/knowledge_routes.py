"""管理路由；批量操作由页面逐文件上传并保留每项结果。"""
from fastapi import Query, Request
from fastapi.responses import FileResponse
from .contracts.knowledge import (
    KnowledgeBase, KnowledgeWrite, KnowledgeUpdate, KnowledgeReference, KnowledgePageRequest,
    KnowledgePage, DocumentVersion, DocumentReadRequest, KnowledgeRevision,
)


def register_knowledge_routes(app):
    repository = app.state.knowledge

    @app.get('/api/v1/knowledge', response_model=list[KnowledgeBase])
    async def list_knowledge():
        return repository.list()

    @app.post('/api/v1/knowledge', response_model=KnowledgeBase, status_code=201)
    async def create_knowledge(value: KnowledgeWrite):
        return repository.create(value)

    @app.put('/api/v1/knowledge/{knowledge_id}', response_model=KnowledgeBase)
    async def update_knowledge(knowledge_id: str, value: KnowledgeUpdate):
        return repository.update(knowledge_id, value)

    @app.get('/api/v1/knowledge/{knowledge_id}/documents', response_model=KnowledgePage)
    async def documents(knowledge_id: str, revision_id: str | None = Query(None, alias='revisionId'),
                        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        reference = repository.resolve(KnowledgeReference(knowledge_id=knowledge_id, revision_id=revision_id))
        return repository.page(KnowledgePageRequest(reference=reference, offset=offset, limit=limit))

    @app.post('/api/v1/knowledge/{knowledge_id}/documents', response_model=DocumentVersion, status_code=201)
    async def import_document(knowledge_id: str, request: Request, name: str = Query(min_length=1, max_length=255),
                              document_id: str | None = Query(None, alias='documentId')):
        return await repository.import_document(knowledge_id, name, request.stream(), document_id)

    @app.delete('/api/v1/knowledge/{knowledge_id}/documents/{document_id}', response_model=KnowledgeRevision)
    async def remove_document(knowledge_id: str, document_id: str):
        return repository.remove(knowledge_id, document_id)

    @app.get('/api/v1/knowledge/{knowledge_id}/documents/{document_id}/versions', response_model=list[DocumentVersion])
    async def versions(knowledge_id: str, document_id: str):
        return repository.history(knowledge_id, document_id)

    @app.get('/api/v1/knowledge/{knowledge_id}/versions/{version_id}/original')
    async def original(knowledge_id: str, version_id: str):
        # 管理页面可获取逻辑移除前的旧版本，执行块仍必须经过任务绑定检查。
        from .repositories.knowledge import knowledge_error
        raw = repository.versions.get(version_id)
        if raw is None or raw['knowledge_id'] != knowledge_id:
            raise knowledge_error('KNOWLEDGE_NOT_FOUND', '文档版本不存在', 404)
        revision = next(r for r in repository.revisions.values()
                        if r['knowledge_id'] == knowledge_id and version_id in r['versions'])
        reference = repository.resolve(KnowledgeReference(knowledge_id=knowledge_id, revision_id=revision['revision_id']))
        value = DocumentReadRequest(reference=reference, version_id=version_id)
        metadata = repository.metadata(value)
        return FileResponse(repository.original(value), filename=metadata.original_name,
                            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
