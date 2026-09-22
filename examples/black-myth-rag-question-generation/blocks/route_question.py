# BEGIN GENERATED CONTRACTS
"""知识库出题业务的唯一契约源；资源通过 sync_contracts.py 嵌入，不依赖工作区路径。"""
import re
from typing import Annotated, Literal

from pydantic import Field, model_validator
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.knowledge import TaskKnowledge
from agent_platform.contracts.retrieval import EvidenceContext, Citation, RetrievalLimits

Text = Annotated[str, Field(min_length=1, pattern=r'\S')]
Kind = Literal['single_choice', 'true_false', 'essay']
QuestionId = Annotated[str, Field(pattern=r'^(choice|judgment|essay)-[1-9][0-9]*$')]
PREFIXES = {'single_choice': 'choice', 'true_false': 'judgment', 'essay': 'essay'}
KINDS = ['single_choice', 'true_false', 'essay']


class Request(StrictModel):
    requirement: Text = Field(max_length=10000, description='自然语言主题、题型和数量要求。')
    knowledge: TaskKnowledge
    limits: RetrievalLimits = Field(default_factory=RetrievalLimits)


class Demand(StrictModel):
    type: Text = Field(description='规范题型或原始不支持题型；不能把填空等改为判断。')
    count: int = Field(description='请求数量，无业务上限；规范化检查非负且总数至少为一。')


class ParsedRequest(StrictModel):
    topic: Text
    demands: list[Demand]
    terms: list[Text] = Field(max_length=30)
    unsupported_constraints: list[Text] = Field(max_length=30, description='不能确定或无法满足的要求；题型内的不同数量不是不支持约束。')


class RequestItem(StrictModel):
    question_id: QuestionId
    type: Kind


class Normalized(StrictModel):
    request: Request
    parsed: ParsedRequest
    supported: bool
    reason: Text
    items: list[RequestItem]


class PlanItem(RequestItem):
    knowledge_point: Text
    objective: Text
    evidence: list[Citation] = Field(min_length=1, max_length=20)


class Missing(StrictModel):
    question_id: QuestionId
    reason: Text


class Sufficient(StrictModel):
    status: Literal['sufficient']
    items: list[PlanItem] = Field(min_length=1)


class Insufficient(StrictModel):
    status: Literal['insufficient_source']
    missing: list[Missing] = Field(min_length=1)
    reason: Text


class Planning(StrictModel):
    decision: Sufficient | Insufficient


class Planned(StrictModel):
    normalized: Normalized
    context: EvidenceContext
    planning: Planning


class Generation(StrictModel):
    item: PlanItem
    context: EvidenceContext


class Choice(StrictModel):
    question_id: Annotated[str, Field(pattern=r'^choice-[1-9][0-9]*$')]
    type: Literal['single_choice']
    stem: Text
    options: list[Text] = Field(min_length=4, max_length=4, description='依次为 A、B、C、D，规范化后互不重复。')
    answer: Literal['A', 'B', 'C', 'D']
    explanation: Text
    evidence: list[Citation] = Field(min_length=1, max_length=20)


class Judgment(StrictModel):
    question_id: Annotated[str, Field(pattern=r'^judgment-[1-9][0-9]*$')]
    type: Literal['true_false']
    stem: Text
    answer: bool = Field(description='严格布尔值；未提及不代表错误。')
    explanation: Text
    correction: str = Field(description='false 时必须给出有依据的纠正；true 时为空字符串。')
    evidence: list[Citation] = Field(min_length=1, max_length=20)


class ScoringPoint(StrictModel):
    criterion: Text
    points: int = Field(ge=1, le=100)


class Essay(StrictModel):
    question_id: Annotated[str, Field(pattern=r'^essay-[1-9][0-9]*$')]
    type: Literal['essay']
    stem: Text
    answer: Text
    scoring_points: list[ScoringPoint] = Field(min_length=1, max_length=20)
    evidence: list[Citation] = Field(min_length=1, max_length=20)


Question = Choice | Judgment | Essay


class QuestionEnvelope(StrictModel):
    question: Question


class Collection(StrictModel):
    # foreach 的静态集合出口不承诺非空；汇总块负责实际请求数量与 ID 覆盖校验。
    items: list[QuestionEnvelope]


class Questions(StrictModel):
    questions: list[Question] = Field(min_length=1)


class Finding(StrictModel):
    question_id: QuestionId
    severity: Literal['blocking', 'advisory']
    reason: Text
    suggestion: Text
    evidence: list[Citation] = Field(max_length=20)


class Review(StrictModel):
    verdict: Literal['pass', 'revise', 'regenerate', 'insufficient_source']
    checked_question_ids: list[QuestionId] = Field(min_length=1)
    findings: list[Finding]
    rationale: Text
    missing: list[Missing]


class ReviewRecord(StrictModel):
    revision_round: int = Field(ge=0, le=2)
    questions: Questions
    review: Review


class State(StrictModel):
    planned: Planned
    current: Questions
    revision_rounds: int = Field(ge=0, le=2)
    history: list[ReviewRecord] = Field(max_length=3)
    awaiting_review: bool


class Completed(StrictModel):
    status: Literal['completed']
    state: State


class InsufficientResult(StrictModel):
    status: Literal['insufficient_source']
    requested_items: list[RequestItem] = Field(min_length=1)
    reason: Text
    missing: list[Missing] = Field(min_length=1)
    context: EvidenceContext
    history: list[ReviewRecord] = Field(max_length=3)


class UnsupportedResult(StrictModel):
    status: Literal['unsupported_request']
    reason: Text
    supported_scope: Literal['single_choice, true_false, essay; arbitrary_counts']
    request: Request


class QualityNotMet(StrictModel):
    status: Literal['quality_not_met']
    reason: Text
    state: State


class Result(StrictModel):
    result: Completed | InsufficientResult | UnsupportedResult | QualityNotMet


def requested_counts(parsed):
    """数量只受实际资源/预算限制，不以固定题量判为不支持。"""
    if parsed.unsupported_constraints or not parsed.demands:
        return None
    counts = dict.fromkeys(KINDS, 0)
    for demand in parsed.demands:
        if demand.type not in counts or demand.count < 0:
            return None
        counts[demand.type] += demand.count
    return counts if sum(counts.values()) > 0 else None


def request_items(parsed):
    counts = requested_counts(parsed)
    if counts is None:
        return []
    return [RequestItem(question_id=f'{PREFIXES[kind]}-{index}', type=kind)
            for kind in KINDS for index in range(1, counts[kind] + 1)]


def check_coverage(items, expected):
    if [(x.question_id, x.type) for x in items] != [(x.question_id, x.type) for x in expected]:
        raise ValueError('题目数量、顺序、稳定 ID 和题型必须完整匹配本次请求')


def check_citations(context, citations):
    context.evidence.verify_selection()
    selected = {e.fragment_id: e for e in context.evidence.selected}
    for citation in citations:
        if citation.fragment_id not in selected or not citation.quote.strip():
            raise ValueError('引用必须来自本次固定修订的选用证据')
        if citation.quote not in selected[citation.fragment_id].text:
            raise ValueError('引文不是声明片段的逐字摘录')


def check_normalized(value):
    counts = requested_counts(value.parsed)
    if value.supported != (counts is not None):
        raise ValueError('支持范围判定与解析要求不一致')
    if counts is not None:
        if len(value.items) != sum(counts.values()):
            raise ValueError('请求展开数量不匹配')
        index = 0
        for kind in KINDS:
            for number in range(1, counts[kind] + 1):
                item = value.items[index]
                if (item.question_id, item.type) != (f'{PREFIXES[kind]}-{number}', kind):
                    raise ValueError('请求 ID 必须按题型分组连续编号')
                index += 1
    elif value.items:
        raise ValueError('不支持的请求不得产生替代题目')


def check_planned(value):
    check_normalized(value.normalized)
    if not value.normalized.supported:
        raise ValueError('不支持的请求不得规划')
    evidence = value.context.evidence
    evidence.verify_selection()
    request = value.normalized.request
    if (request.knowledge.knowledge_id != evidence.reference.knowledge_id
            or request.knowledge.revision_id != evidence.reference.revision_id):
        raise ValueError('证据范围必须等于提交时固定的知识库修订')
    decision = value.planning.decision
    if isinstance(decision, Sufficient):
        check_coverage(decision.items, value.normalized.items)
        if len({(i.knowledge_point.strip().casefold(), i.objective.strip().casefold()) for i in decision.items}) != len(decision.items):
            raise ValueError('规划不得完全重复同一考点和考查目标')
        for item in decision.items:
            check_candidate_text([item.knowledge_point, item.objective], value.context)
            check_citations(value.context, item.evidence)
    else:
        check_missing(decision.missing, value.normalized.items)
    return value


def check_missing(items, expected):
    if not items or len({i.question_id for i in items}) != len(items):
        raise ValueError('缺项必须非空且不能重复题目 ID')
    if not {i.question_id for i in items}.issubset({i.question_id for i in expected}):
        raise ValueError('缺项只能引用本次请求的题目 ID')


def check_candidate_text(texts, context):
    """证据元数据只用于平台追溯，不进入考生阅读、作答或评分内容。"""
    fields = re.compile(r'(?i)(?<![a-z0-9_])(?:fragment_?id|document_?id|version_?id|knowledge_?id|revision_?id|sha256)(?![a-z0-9_])')
    fragments = context.evidence.selected
    identifiers = {identifier.casefold() for fragment in fragments for identifier in (
        fragment.fragment_id, fragment.document_id, fragment.version_id,
        fragment.reference.knowledge_id, fragment.reference.revision_id, fragment.sha256,
    ) if identifier}
    for text in texts:
        if fields.search(text) or any(identifier in text.casefold() for identifier in identifiers):
            raise ValueError('考生内容不得包含平台证据字段或内部标识；溯源仅写入 evidence')


def check_question(question, context):
    check_citations(context, question.evidence)
    texts = [question.stem]
    if isinstance(question, Choice):
        texts.extend([*question.options, question.explanation])
    elif isinstance(question, Judgment):
        texts.extend([question.explanation, question.correction])
    elif isinstance(question, Essay):
        texts.extend([question.answer, *(point.criterion for point in question.scoring_points)])
    check_candidate_text(texts, context)
    if isinstance(question, Choice):
        if len({' '.join(o.split()).casefold() for o in question.options}) != 4:
            raise ValueError('单选题四个选项不得重复')
    if isinstance(question, Judgment):
        if (not question.answer and not question.correction.strip()) or (question.answer and question.correction):
            raise ValueError('错误命题必须纠正，正确命题不得带纠正')
    return question


def check_review(review, context, expected):
    if review.checked_question_ids != [item.question_id for item in expected]:
        raise ValueError('审题必须按请求顺序完整覆盖本次所有题目')
    if not {f.question_id for f in review.findings}.issubset(set(review.checked_question_ids)):
        raise ValueError('审查意见不能引用请求之外的题目')
    if review.verdict == 'pass' and any(f.severity == 'blocking' for f in review.findings):
        raise ValueError('有阻断问题不能通过')
    if review.verdict in ('revise', 'regenerate') and not any(f.severity == 'blocking' for f in review.findings):
        raise ValueError('修订与重出必须指出阻断问题')
    if review.verdict == 'insufficient_source':
        check_missing(review.missing, expected)
    elif review.missing:
        raise ValueError('仅资料不足结论允许声明缺项')
    for finding in review.findings:
        check_citations(context, finding.evidence)


def check_state(state):
    check_planned(state.planned)
    if not isinstance(state.planned.planning.decision, Sufficient):
        raise ValueError('资料不足不能产生题目状态')
    check_coverage(state.current.questions, state.planned.normalized.items)
    for question in state.current.questions:
        check_question(question, state.planned.context)
    expected = state.revision_rounds + (0 if state.awaiting_review else 1)
    if len(state.history) != expected:
        raise ValueError('审查历史必须逐轮保留，最新题目必须重新审查')
    for index, record in enumerate(state.history):
        if record.revision_round != index:
            raise ValueError('审查轮数不连续')
        check_coverage(record.questions.questions, state.planned.normalized.items)
        for question in record.questions.questions:
            check_question(question, state.planned.context)
        check_review(record.review, state.planned.context, state.planned.normalized.items)
        if index < state.revision_rounds and record.review.verdict not in ('revise', 'regenerate'):
            raise ValueError('只有修订或重出结论允许进入下一轮')
    if not state.awaiting_review and state.history[-1].questions != state.current:
        raise ValueError('最新审查必须针对当前题目')
    return state


def check_result(value):
    result = value.result
    if isinstance(result, (Completed, QualityNotMet)):
        state = check_state(result.state)
        if state.awaiting_review:
            raise ValueError('未经审查的题目不能作为最终结果')
        verdict = state.history[-1].review.verdict
        if isinstance(result, Completed) and verdict != 'pass':
            raise ValueError('仅审题通过可以交付合格题目')
        if isinstance(result, QualityNotMet) and (verdict not in ('revise', 'regenerate') or state.revision_rounds != 2):
            raise ValueError('仅两轮修订耗尽仍未通过可以返回质量未达标')
    elif isinstance(result, InsufficientResult):
        check_missing(result.missing, result.requested_items)
        result.context.evidence.verify_selection()
        for record in result.history:
            check_coverage(record.questions.questions, result.requested_items)
            check_review(record.review, result.context, result.requested_items)
    return value


class ValidatedResult(Result):
    """最终生产端执行关系校验；消费端使用结构相同的 Result 端口。"""
    @model_validator(mode='after')
    def validate_result(self):
        return check_result(self)
# END GENERATED CONTRACTS

from agent_platform.blocks import block
from agent_platform.contracts.retrieval import RetrievalRequest

@block(id='rag-question-route-question', version='4.0.0', name='三类题型路由', description='主数据 Generation；参考 tuple[()]；输出 Kind。')
def run(value: NodeInput[Generation, tuple[()]]) -> Kind:
    try:
        return value.primary.item.type
    except ValueError as exc:
        from agent_platform.contracts.errors import ErrorResponse, PlatformError
        raise PlatformError(ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='block.rag_question', message=str(exc))) from None
