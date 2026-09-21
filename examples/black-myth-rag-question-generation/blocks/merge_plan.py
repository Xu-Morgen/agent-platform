# BEGIN GENERATED CONTRACTS
"""知识库三题业务的唯一契约源；资源通过 sync_contracts.py 嵌入，不依赖工作区路径。"""
from typing import Annotated, Literal

from pydantic import Field, model_validator
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.knowledge import TaskKnowledge
from agent_platform.contracts.retrieval import EvidenceContext, Citation, RetrievalLimits

Text = Annotated[str, Field(min_length=1, pattern=r'\S')]
Kind = Literal['single_choice', 'true_false', 'essay']
QuestionId = Literal['choice-1', 'judgment-1', 'essay-1']
IDS = ['choice-1', 'judgment-1', 'essay-1']
KINDS = ['single_choice', 'true_false', 'essay']


class Request(StrictModel):
    requirement: Text = Field(max_length=10000, description='自然语言主题、题型和数量要求。')
    knowledge: TaskKnowledge
    limits: RetrievalLimits = Field(default_factory=RetrievalLimits)


class Demand(StrictModel):
    type: Text = Field(description='规范题型或原始不支持题型；不能把填空等改为判断。')
    count: int = Field(ge=0, le=10000)


class ParsedRequest(StrictModel):
    topic: Text
    demands: list[Demand] = Field(max_length=30)
    terms: list[Text] = Field(max_length=30)
    unsupported_constraints: list[Text] = Field(max_length=30, description='首版不能满足的其他要求，不得静默丢弃。')


class RequestItem(StrictModel):
    question_id: QuestionId
    type: Kind


class Normalized(StrictModel):
    request: Request
    parsed: ParsedRequest
    supported: bool
    reason: Text
    items: list[RequestItem] = Field(max_length=3)


class PlanItem(RequestItem):
    knowledge_point: Text
    objective: Text
    evidence: list[Citation] = Field(min_length=1, max_length=20)


class Missing(StrictModel):
    question_id: QuestionId
    reason: Text


class Sufficient(StrictModel):
    status: Literal['sufficient']
    items: list[PlanItem] = Field(min_length=3, max_length=3)


class Insufficient(StrictModel):
    status: Literal['insufficient_source']
    missing: list[Missing] = Field(min_length=1, max_length=3)
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
    question_id: Literal['choice-1']
    type: Literal['single_choice']
    stem: Text
    options: list[Text] = Field(min_length=4, max_length=4, description='依次为 A、B、C、D，规范化后互不重复。')
    answer: Literal['A', 'B', 'C', 'D']
    explanation: Text
    evidence: list[Citation] = Field(min_length=1, max_length=20)


class Judgment(StrictModel):
    question_id: Literal['judgment-1']
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
    question_id: Literal['essay-1']
    type: Literal['essay']
    stem: Text
    answer: Text
    scoring_points: list[ScoringPoint] = Field(min_length=1, max_length=20)
    evidence: list[Citation] = Field(min_length=1, max_length=20)


Question = Choice | Judgment | Essay


class QuestionEnvelope(StrictModel):
    question: Question


class Collection(StrictModel):
    # foreach 的静态集合出口不承诺非空；汇总块负责准确三题校验。
    items: list[QuestionEnvelope]


class Questions(StrictModel):
    questions: list[Question] = Field(min_length=3, max_length=3)


class Finding(StrictModel):
    question_id: QuestionId
    severity: Literal['blocking', 'advisory']
    reason: Text
    suggestion: Text
    evidence: list[Citation] = Field(max_length=20)


class Review(StrictModel):
    verdict: Literal['pass', 'revise', 'regenerate', 'insufficient_source']
    checked_question_ids: list[QuestionId] = Field(min_length=3, max_length=3)
    findings: list[Finding] = Field(max_length=30)
    rationale: Text
    missing: list[Missing] = Field(max_length=3)


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
    reason: Text
    missing: list[Missing] = Field(min_length=1, max_length=3)
    context: EvidenceContext
    history: list[ReviewRecord] = Field(max_length=3)


class UnsupportedResult(StrictModel):
    status: Literal['unsupported_request']
    reason: Text
    supported_scope: Literal['single_choice=1, true_false=1, essay=1']
    request: Request


class QualityNotMet(StrictModel):
    status: Literal['quality_not_met']
    reason: Text
    state: State


class Result(StrictModel):
    result: Completed | InsufficientResult | UnsupportedResult | QualityNotMet


def check_coverage(items):
    if [(x.question_id, x.type) for x in items] != list(zip(IDS, KINDS)):
        raise ValueError('必须按单选、判断、论述顺序各一题，且稳定 ID 与题型对应')


def check_citations(context, citations):
    context.evidence.verify_selection()
    selected = {e.fragment_id: e for e in context.evidence.selected}
    for citation in citations:
        if citation.fragment_id not in selected or not citation.quote.strip():
            raise ValueError('引用必须来自本次固定修订的选用证据')
        if citation.quote not in selected[citation.fragment_id].text:
            raise ValueError('引文不是声明片段的逐字摘录')


def check_normalized(value):
    counts = {}
    for demand in value.parsed.demands:
        counts[demand.type] = counts.get(demand.type, 0) + demand.count
    supported = counts == dict.fromkeys(KINDS, 1) and not value.parsed.unsupported_constraints
    if value.supported != supported:
        raise ValueError('支持范围判定与解析要求不一致')
    if supported:
        check_coverage(value.items)
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
        check_coverage(decision.items)
        if len({i.knowledge_point.strip().casefold() for i in decision.items}) != 3:
            raise ValueError('规划必须覆盖三个不同考点')
        for item in decision.items:
            check_citations(value.context, item.evidence)
    else:
        check_missing(decision.missing)
    return value


def check_missing(items):
    if not items or len({i.question_id for i in items}) != len(items):
        raise ValueError('缺项必须非空且不能重复题目 ID')


def check_question(question, context):
    check_citations(context, question.evidence)
    if isinstance(question, Choice):
        if len({' '.join(o.split()).casefold() for o in question.options}) != 4:
            raise ValueError('单选题四个选项不得重复')
    if isinstance(question, Judgment):
        if (not question.answer and not question.correction.strip()) or (question.answer and question.correction):
            raise ValueError('错误命题必须纠正，正确命题不得带纠正')
    return question


def check_review(review, context):
    if review.checked_question_ids != IDS:
        raise ValueError('审题必须完整覆盖三题')
    if review.verdict == 'pass' and any(f.severity == 'blocking' for f in review.findings):
        raise ValueError('有阻断问题不能通过')
    if review.verdict in ('revise', 'regenerate') and not any(f.severity == 'blocking' for f in review.findings):
        raise ValueError('修订与重出必须指出阻断问题')
    if review.verdict == 'insufficient_source':
        check_missing(review.missing)
    elif review.missing:
        raise ValueError('仅资料不足结论允许声明缺项')
    for finding in review.findings:
        check_citations(context, finding.evidence)


def check_state(state):
    check_planned(state.planned)
    if not isinstance(state.planned.planning.decision, Sufficient):
        raise ValueError('资料不足不能产生题目状态')
    check_coverage(state.current.questions)
    for question in state.current.questions:
        check_question(question, state.planned.context)
    expected = state.revision_rounds + (0 if state.awaiting_review else 1)
    if len(state.history) != expected:
        raise ValueError('审查历史必须逐轮保留，最新题目必须重新审查')
    for index, record in enumerate(state.history):
        if record.revision_round != index:
            raise ValueError('审查轮数不连续')
        check_coverage(record.questions.questions)
        for question in record.questions.questions:
            check_question(question, state.planned.context)
        check_review(record.review, state.planned.context)
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
        check_missing(result.missing)
        result.context.evidence.verify_selection()
        for record in result.history:
            check_review(record.review, result.context)
    return value


class ValidatedResult(Result):
    """最终生产端执行关系校验；消费端使用结构相同的 Result 端口。"""
    @model_validator(mode='after')
    def validate_result(self):
        return check_result(self)
# END GENERATED CONTRACTS

from agent_platform.blocks import block
from agent_platform.contracts.retrieval import RetrievalRequest

@block(id='rag-question-merge-plan', version='1.0.0', name='合并并核验三题规划', description='主数据 Planning；参考 tuple[EvidenceContext, Normalized]；输出 Planned。')
def run(value: NodeInput[Planning, tuple[EvidenceContext, Normalized]]) -> Planned:
    result = Planned(normalized=value.references[1], context=value.references[0], planning=value.primary)
    return check_planned(result)
