"""证据保持完整片段；上下文不足时跳过过长片段并明确记录限制。"""
from agent_platform.blocks import block
from agent_platform.blocks.context import BlockContext
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.knowledge import EvidenceRegistration
from agent_platform.contracts.retrieval import SearchResults, EvidenceContext


@block(id='rag-select-evidence', version='1.0.0', name='整理并登记证据', description='按 topK 与上下文字符总量选择完整片段；记录扫描范围、全部实际候选、选用片段和参数。无参考输入。')
async def run(value: NodeInput[SearchResults, tuple[()]], *, context: BlockContext) -> EvidenceContext:
    result = value.primary
    limits = result.corpus.selection.request.limits
    selected, used = [], 0
    for candidate in result.candidates:
        if len(selected) >= limits.top_k:
            break
        if used + len(candidate.text) <= limits.context_characters:
            selected.append(candidate)
            used += len(candidate.text)
    evidence = EvidenceRegistration(query=result.corpus.selection.request.query,
        reference=result.corpus.selection.reference, scanned_versions=result.corpus.scanned_versions,
        scope_limited=result.corpus.scope_limited, candidates=result.candidates, selected=selected,
        parameters={'limits': limits.model_dump(mode='json', by_alias=True), 'terms': result.terms, 'algorithm': result.algorithm})
    await context.knowledge_record(evidence)
    return EvidenceContext(evidence=evidence, terms=result.terms, algorithm=result.algorithm,
                           context_limited=len(selected) < len(result.candidates))
