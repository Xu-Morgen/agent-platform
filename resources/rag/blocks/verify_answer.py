"""精确引文核验不代表模型答案语义正确；结果携带固定证据供人工追溯。"""
from agent_platform.blocks import block
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.retrieval import GroundedAnswer, EvidenceContext, VerifiedAnswer
from agent_platform.contracts.errors import PlatformError, ErrorResponse


@block(id='rag-verify-answer', version='1.0.0', name='核验回答引用', description='主数据为模型回答，参考输入为生成时的证据上下文；检查每条引文确实来自本次选用证据。语义正确性仍需审查。')
def run(value: NodeInput[GroundedAnswer, tuple[EvidenceContext]]) -> VerifiedAnswer:
    try:
        value.primary.citations_required()
        value.references[0].evidence.verify_selection()
    except ValueError as exc:
        raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='rag.citations', message=str(exc))) from None
    context = value.references[0]
    selected = {item.fragment_id: item for item in context.evidence.selected}
    for citation in value.primary.citations:
        if citation.fragment_id not in selected or citation.quote not in selected[citation.fragment_id].text:
            raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='rag.citations', message='引用不属于本次选用证据或引文与规范化原文不一致'))
    return VerifiedAnswer(result=value.primary, context=context)
