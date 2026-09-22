"""默认本地语义检索：使用任务固定模型，按 tokenizer 显式切分并保留来源。"""
from agent_platform.blocks import block
from agent_platform.blocks.context import BlockContext
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.retrieval import ParsedCorpus, SearchResults
from agent_platform.contracts.embedding import SemanticSearchRequest
from agent_platform.contracts.errors import PlatformError, ErrorResponse


@block(id='rag-semantic-search', version='2.0.0', name='本地语义检索',
       description='使用任务固定的本地 CPU 模型；tokenizer 切分保留字符定位，余弦 topK 不代表材料足以回答。无参考输入。',
       semanticSearch=True)
async def run(value: NodeInput[ParsedCorpus, tuple[()]], *, context: BlockContext) -> SearchResults:
    corpus = value.primary
    limits = corpus.selection.request.limits
    request = SemanticSearchRequest(reference=corpus.selection.reference,
        query=corpus.selection.request.query, fragments=corpus.fragments,
        splitter='rag-semantic-search@1.0.0:tokenizer-offset-v1',
        scope_limited=corpus.scope_limited, top_k=limits.top_k)
    request = await context.semantic_split(request)
    if len(request.fragments) > limits.max_fragments:
        raise PlatformError(ErrorResponse(code='EMBEDDING_INPUT_LIMIT', stage='rag.semantic',
            message='tokenizer 切分后超过本次 maxFragments；请明确调整读取范围或片段上限'))
    context.progress('本地语义检索', current=0, total=len(request.fragments))
    result = await context.semantic_search(request)
    corpus = corpus.model_copy(update={'fragments': request.fragments})
    context.progress('本地语义检索完成', current=len(request.fragments), total=len(request.fragments))
    return SearchResults(corpus=corpus, terms=[], candidates=result.candidates,
                         algorithm=f'{result.algorithm}:{result.model.model_id}:{result.splitter}')
