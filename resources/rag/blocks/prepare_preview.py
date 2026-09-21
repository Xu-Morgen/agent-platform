"""为单份指定版本构造普通读取输入；后接相同 DOCX 读取块。"""
from agent_platform.blocks import block
from agent_platform.blocks.context import BlockContext
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.knowledge import DocumentReadRequest
from agent_platform.contracts.retrieval import DocumentPreviewRequest, DocumentSelection, RetrievalRequest


@block(id='rag-prepare-preview', version='1.0.0', name='准备文档预览', description='指定知识库及文档版本，后接普通 DOCX 读取块；无模型调用，无参考输入。')
async def run(value: NodeInput[DocumentPreviewRequest, tuple[()]], *, context: BlockContext) -> DocumentSelection:
    request = value.primary
    reference = await context.knowledge_resolve(request.knowledge)
    document = await context.knowledge_metadata(DocumentReadRequest(reference=reference,
        version_id=request.version_id, max_bytes=request.limits.max_file_bytes))
    return DocumentSelection(request=RetrievalRequest(knowledge=reference, query='文档预览', limits=request.limits),
        reference=reference, documents=[document], total_documents=1, scope_limited=False)
