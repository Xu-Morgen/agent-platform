# BEGIN GENERATED CONTRACTS
"""出题质量权威契约；由 sync_contracts.py 原样嵌入自包含资源，勿手改副本。"""
import re
from typing import Annotated, Literal

from pydantic import Field, model_validator
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput

NonBlank = Annotated[str, Field(min_length=1, pattern=r'\S')]
QuestionId = Literal['essay-1', 'choice-1', 'blank-1']
QuestionType = Literal['essay', 'single_choice', 'fill_blank']


class Document(StrictModel):
    file_name: NonBlank
    text: NonBlank
    numbered_text: NonBlank


class Evidence(StrictModel):
    # 行号针对读取块完整 text.splitlines()，从 1 开始；不把 DOCX 行号伪称页码。
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: NonBlank


class PlanItem(StrictModel):
    question_id: QuestionId
    type: QuestionType
    knowledge_point: NonBlank
    objective: NonBlank
    difficulty: Literal['easy', 'medium', 'hard']
    evidence: list[Evidence] = Field(min_length=1)


class SufficientPlan(StrictModel):
    status: Literal['sufficient']
    items: list[PlanItem] = Field(min_length=3, max_length=3)


class InsufficientPlan(StrictModel):
    status: Literal['insufficient_source']
    reason: NonBlank


class Planning(StrictModel):
    decision: SufficientPlan | InsufficientPlan


class Options(StrictModel):
    A: NonBlank = Field(alias='A')
    B: NonBlank = Field(alias='B')
    C: NonBlank = Field(alias='C')
    D: NonBlank = Field(alias='D')


class Essay(StrictModel):
    question_id: Literal['essay-1']
    type: Literal['essay']
    stem: NonBlank
    reference_answer: NonBlank
    scoring_points: list[NonBlank] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class SingleChoice(StrictModel):
    question_id: Literal['choice-1']
    type: Literal['single_choice']
    stem: NonBlank
    options: Options
    reference_answer: Literal['A', 'B', 'C', 'D']
    explanation: NonBlank
    evidence: list[Evidence] = Field(min_length=1)


class FillBlank(StrictModel):
    question_id: Literal['blank-1']
    type: Literal['fill_blank']
    stem: Annotated[str, Field(min_length=1, pattern=r'____')]
    reference_answers: list[NonBlank] = Field(min_length=1)
    # 每空一组可接受的同义表述，至少包含主答案。
    accepted_answers: list[list[NonBlank]] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class Questions(StrictModel):
    questions: list[Essay | SingleChoice | FillBlank] = Field(min_length=3, max_length=3)


def check_questions(value):
    if [q.type for q in value.questions] != ['essay', 'single_choice', 'fill_blank']:
        raise ValueError('必须依次包含论述题、单选题、填空题各一道，ID 固定')
    options = value.questions[1].options
    normalized = [re.sub(r'\s+', ' ', s).strip().casefold() for s in (options.A, options.B, options.C, options.D)]
    if len(set(normalized)) != 4:
        raise ValueError('四个选项不得重复')
    blank = value.questions[2]
    slots = re.findall(r'_+', blank.stem)
    if any(s != '____' for s in slots) or len(slots) != len(blank.reference_answers):
        raise ValueError('空位必须为四下划线且与答案数量一致')
    if len(blank.accepted_answers) != len(slots) or any(
        answer not in accepted for answer, accepted in zip(blank.reference_answers, blank.accepted_answers)
    ):
        raise ValueError('每空必须明确接受范围并包含主答案')
    return value


class GeneratedQuestions(Questions):
    # 输出端执行关系校验；消费端用结构契约，由确定性块再次检查关系。
    # 不声称不同资源的自定义 validator 具有同一平台契约身份。
    @model_validator(mode='after')
    def valid_questions(self):
        return check_questions(self)


class Finding(StrictModel):
    question_id: QuestionId
    code: Literal['unsupported', 'incorrect_answer', 'ambiguous', 'weak_distractor',
                  'unscorable', 'coverage', 'difficulty', 'answer_leak', 'other']
    severity: Literal['blocking', 'advisory']
    reason: NonBlank
    evidence: list[Evidence] = Field(min_length=1)
    suggestion: NonBlank


class Review(StrictModel):
    phase: Literal['reviewed']
    verdict: Literal['pass', 'revise', 'regenerate', 'insufficient_source']
    checked_question_ids: list[QuestionId] = Field(min_length=3, max_length=3)
    findings: list[Finding]
    rationale: NonBlank


def check_review(value):
    if value.checked_question_ids != ['essay-1', 'choice-1', 'blank-1']:
        raise ValueError('审题必须按固定顺序覆盖所有题目')
    if value.verdict == 'pass' and any(f.severity == 'blocking' for f in value.findings):
        raise ValueError('pass 不得携带阻断问题')
    if value.verdict in ('revise', 'regenerate') and not value.findings:
        raise ValueError('修订或重新出题必须记录具体问题')
    return value


class ReviewResult(Review):
    @model_validator(mode='after')
    def valid_review(self):
        return check_review(self)


class AwaitingReview(StrictModel):
    phase: Literal['awaiting_review']


class QuestionState(StrictModel):
    document: Document
    plan: SufficientPlan
    current: Questions
    review: AwaitingReview | Review
    revision_rounds: int = Field(ge=0, le=2)


class GenerationInput(StrictModel):
    # 初稿与重新出题共用包，两个阶段都由 Python 准备主数据。
    context: SufficientPlan | QuestionState


class PlannerEntry(NodeInput[Document, tuple[()]]):
    pass


class GeneratorEntry(NodeInput[GenerationInput, tuple[Document, SufficientPlan]]):
    pass


class StateEntry(NodeInput[QuestionState, tuple[()]]):
    pass


def quality_fail(message, *, insufficient=False, field_path=None):
    from agent_platform.contracts.errors import ErrorResponse, PlatformError
    raise PlatformError(ErrorResponse(
        code='PACKAGE_INPUT_INSUFFICIENT' if insufficient else 'CONTRACT_VALIDATION_ERROR',
        stage='block.question_quality', message=message, field_path=field_path,
    ))


def verify_evidence(document, evidence, *, owner, field_path):
    lines = document.text.splitlines()
    for index, item in enumerate(evidence):
        path = [*field_path, index]
        location = f'{owner} 的第 {index + 1} 条依据（声明第 {item.start_line}–{item.end_line} 行）'
        if item.end_line < item.start_line or item.end_line > len(lines):
            quality_fail(location + f'：行号无效，原文共 {len(lines)} 行', field_path=path)
        if item.quote not in '\n'.join(lines[item.start_line - 1:item.end_line]):
            quality_fail(location + '：引文不在声明范围内；请根据 numberedText 的显式编号核对，不要自行数行',
                         field_path=path)


def verify_plan(document, plan):
    expected = '\n'.join(f'{index}: {line}' for index, line in enumerate(document.text.splitlines(), 1))
    if document.numbered_text != expected:
        quality_fail('原文行号索引与正文不一致', field_path=['document', 'numberedText'])
    if [(item.question_id, item.type) for item in plan.items] != [
        ('essay-1', 'essay'), ('choice-1', 'single_choice'), ('blank-1', 'fill_blank')
    ]:
        quality_fail('规划题型、数量或稳定 ID 不符合要求')
    points = [item.knowledge_point.strip().casefold() for item in plan.items]
    if len(set(points)) != 3:
        quality_fail('规划必须选择三个不同知识点')
    for index, item in enumerate(plan.items):
        verify_evidence(document, item.evidence, owner='规划 ' + item.question_id,
                        field_path=['plan', 'items', index, 'evidence'])


def verify_state(state):
    verify_plan(state.document, state.plan)
    try:
        check_questions(state.current)
        if isinstance(state.review, Review):
            check_review(state.review)
    except ValueError as exc:
        quality_fail(str(exc))
    for index, question in enumerate(state.current.questions):
        verify_evidence(state.document, question.evidence, owner='题目 ' + question.question_id,
                        field_path=['current', 'questions', index, 'evidence'])
    if isinstance(state.review, Review):
        for index, finding in enumerate(state.review.findings):
            verify_evidence(state.document, finding.evidence, owner='审题 ' + finding.question_id,
                            field_path=['review', 'findings', index, 'evidence'])
    return state
# END GENERATED CONTRACTS

Entry = StateEntry
Output = GeneratedQuestions
