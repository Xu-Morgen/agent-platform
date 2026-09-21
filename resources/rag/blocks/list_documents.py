"""在固定修订中按文档上限列举；所有限制来自服务输入。"""
from agent_platform.blocks import block
from agent_platform.blocks.context import BlockContext
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.knowledge import KnowledgePageRequest
from agent_platform.contracts.retrieval import RetrievalRequest, DocumentSelection


@block(id='rag-list-documents', version='1.0.0', name='列举知识库文档', description='固定任务知识库修订并有界列举 DOCX；不读取正文，无参考输入。')
async def run(value: NodeInput[RetrievalRequest, tuple[()]], *, context: BlockContext) -> DocumentSelection:
    reference = await context.knowledge_resolve(value.primary.knowledge)
    page = await context.knowledge_list(KnowledgePageRequest(reference=reference, limit=value.primary.limits.max_documents))
    return DocumentSelection(request=value.primary, reference=reference, documents=page.items,
                             total_documents=page.total, scope_limited=page.next_offset is not None)
