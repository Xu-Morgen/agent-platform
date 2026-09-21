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
    """原文来源：文档读取块输出，规划包输入；正文与行号索引必须一致。"""
    file_name: NonBlank = Field(description='上传文档的原始文件名，用于辨认题目依据的来源。')
    text: NonBlank = Field(description='完整原文正文，供出题与引文核验使用；不截断或概括。')
    numbered_text: NonBlank = Field(description='带有从 1 开始显式行号的完整正文；出题及审题引用这些行号，不作为页码。')


class Evidence(StrictModel):
    """可回查到原文的证据片段，供确定性核验使用。"""
    # 行号针对读取块完整 text.splitlines()，从 1 开始；不把 DOCX 行号伪称页码。
    start_line: int = Field(ge=1, description='引文起始行（含），对应原文 text.splitlines()，从 1 开始。')
    end_line: int = Field(ge=1, description='引文结束行（含），不得早于起始行或超过原文。')
    quote: NonBlank = Field(description='从声明行号范围逐字摘录的原文，用于核验依据真实存在。')


class PlanItem(StrictModel):
    """一题的出题意图、难度和原文依据。"""
    question_id: QuestionId = Field(description='稳定题目标识：essay-1 论述题、choice-1 单选题、blank-1 填空题；用于关联规划、审题与修订。')
    type: QuestionType = Field(description='题型标记：essay 论述、single_choice 单选、fill_blank 填空。')
    knowledge_point: NonBlank = Field(description='本题考查的具体知识点；三题规划应覆盖不同知识点。')
    objective: NonBlank = Field(description='希望通过本题检验的理解或应用能力，指导出题与审题。')
    difficulty: Literal['easy', 'medium', 'hard'] = Field(description='预期难度：easy 基础、medium 理解应用、hard 综合分析。')
    evidence: list[Evidence] = Field(min_length=1, description='支持本题、规划或审题意见的原文引文及行号；确定性块逐条核验。')


class SufficientPlan(StrictModel):
    """可执行的三题规划，由核验规划块交给出题步骤。"""
    status: Literal['sufficient'] = Field(description='资料判定：sufficient 可据此出题；insufficient_source 表示原文不足。')
    items: list[PlanItem] = Field(min_length=3, max_length=3, description='按论述、单选、填空顺序的三个出题规划，每项包含不同知识点及原文依据。')


class InsufficientPlan(StrictModel):
    """原文不足的明确结果，不能当作成功规划继续出题。"""
    status: Literal['insufficient_source'] = Field(description='资料判定：sufficient 可据此出题；insufficient_source 表示原文不足。')
    reason: NonBlank = Field(description='该判定或问题的具体原因，说明缺少什么资料或题目哪里不成立。')


class Planning(StrictModel):
    """规划包输出，下一步由核验块分辨资料是否足够。"""
    decision: SufficientPlan | InsufficientPlan = Field(description='出题规划结果：资料充足时携带三题规划，资料不足时携带原因。')


class Options(StrictModel):
    """单选题选项集合。"""
    A: NonBlank = Field(alias='A', description='单选题 A 选项正文；四个选项内容不得重复。')
    B: NonBlank = Field(alias='B', description='单选题 B 选项正文；四个选项内容不得重复。')
    C: NonBlank = Field(alias='C', description='单选题 C 选项正文；四个选项内容不得重复。')
    D: NonBlank = Field(alias='D', description='单选题 D 选项正文；四个选项内容不得重复。')


class Essay(StrictModel):
    """论述题：题干、参考答案、得分点与原文依据。"""
    question_id: Literal['essay-1'] = Field(description='稳定题目标识：essay-1 论述题、choice-1 单选题、blank-1 填空题；用于关联规划、审题与修订。')
    type: Literal['essay'] = Field(description='题型标记：essay 论述、single_choice 单选、fill_blank 填空。')
    stem: NonBlank = Field(description='展示给答题者的题干；填空题用连续四个下划线 ____ 标示每个空位。')
    reference_answer: NonBlank = Field(description='标准答案；论述题为参考作答，单选题为唯一正确选项字母。')
    scoring_points: list[NonBlank] = Field(min_length=1, description='论述题的具体得分要点，供判分和审查可评分性。')
    evidence: list[Evidence] = Field(min_length=1, description='支持本题、规划或审题意见的原文引文及行号；确定性块逐条核验。')


class SingleChoice(StrictModel):
    """单选题：四个选项、唯一答案及解释。"""
    question_id: Literal['choice-1'] = Field(description='稳定题目标识：essay-1 论述题、choice-1 单选题、blank-1 填空题；用于关联规划、审题与修订。')
    type: Literal['single_choice'] = Field(description='题型标记：essay 论述、single_choice 单选、fill_blank 填空。')
    stem: NonBlank = Field(description='展示给答题者的题干；填空题用连续四个下划线 ____ 标示每个空位。')
    options: Options = Field(description='单选题的 A、B、C、D 四个选项；应有唯一正确答案及有效干扰项。')
    reference_answer: Literal['A', 'B', 'C', 'D'] = Field(description='标准答案；论述题为参考作答，单选题为唯一正确选项字母。')
    explanation: NonBlank = Field(description='说明单选题正确答案成立的原因，并依据原文排除歧义。')
    evidence: list[Evidence] = Field(min_length=1, description='支持本题、规划或审题意见的原文引文及行号；确定性块逐条核验。')


class FillBlank(StrictModel):
    """填空题：显式空位、主答案与可接受答案范围。"""
    question_id: Literal['blank-1'] = Field(description='稳定题目标识：essay-1 论述题、choice-1 单选题、blank-1 填空题；用于关联规划、审题与修订。')
    type: Literal['fill_blank'] = Field(description='题型标记：essay 论述、single_choice 单选、fill_blank 填空。')
    stem: Annotated[str, Field(min_length=1, pattern=r'____')] = Field(description='展示给答题者的题干；填空题用连续四个下划线 ____ 标示每个空位。')
    reference_answers: list[NonBlank] = Field(min_length=1, description='按题干空位顺序列出的主答案，数量必须与空位一致。')
    # 每空一组可接受的同义表述，至少包含主答案。
    accepted_answers: list[list[NonBlank]] = Field(min_length=1, description='每个空位可接受的答案列表；与空位顺序对应，且必须包含该空的主答案。')
    evidence: list[Evidence] = Field(min_length=1, description='支持本题、规划或审题意见的原文引文及行号；确定性块逐条核验。')


class Questions(StrictModel):
    """三题的结构契约，供消费端接收；关系约束另由核验块检查。"""
    questions: list[Essay | SingleChoice | FillBlank] = Field(min_length=3, max_length=3, description='固定顺序的三道题：论述、单选、填空各一道；包含答案和可核验的原文依据。')


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
    """出题与修订包的输出，在结构校验之外检查题型顺序、选项与空位答案关系。"""
    # 输出端执行关系校验；消费端用结构契约，由确定性块再次检查关系。
    # 不声称不同资源的自定义 validator 具有同一平台契约身份。
    @model_validator(mode='after')
    def valid_questions(self):
        return check_questions(self)


class Finding(StrictModel):
    """关联到稳定题目 ID 的一条审题意见。"""
    question_id: QuestionId = Field(description='稳定题目标识：essay-1 论述题、choice-1 单选题、blank-1 填空题；用于关联规划、审题与修订。')
    code: Literal['unsupported', 'incorrect_answer', 'ambiguous', 'weak_distractor',
                  'unscorable', 'coverage', 'difficulty', 'answer_leak', 'other'] = Field(description='问题类别：依据缺失、答案错误、歧义、干扰项弱、不可评分、覆盖、难度、泄露答案或其他。')
    severity: Literal['blocking', 'advisory'] = Field(description='blocking 阻止通过；advisory 为改进建议，不单独阻断通过。')
    reason: NonBlank = Field(description='该判定或问题的具体原因，说明缺少什么资料或题目哪里不成立。')
    evidence: list[Evidence] = Field(min_length=1, description='支持本题、规划或审题意见的原文引文及行号；确定性块逐条核验。')
    suggestion: NonBlank = Field(description='针对该题的可操作修改建议，供定向修订包使用。')


class Review(StrictModel):
    """审题结果的结构契约，供合并审题块接收。"""
    phase: Literal['reviewed'] = Field(description='审题阶段：awaiting_review 待审；reviewed 已完成审题。')
    verdict: Literal['pass', 'revise', 'regenerate', 'insufficient_source'] = Field(description='pass 通过；revise 定向修订；regenerate 重新出题；insufficient_source 原文不足。')
    checked_question_ids: list[QuestionId] = Field(min_length=3, max_length=3, description='按固定顺序记录已审查的三个题目 ID，必须覆盖全部题目。')
    findings: list[Finding] = Field(description='逐题问题清单；修订或重新出题时不能为空，通过时不得保留阻断问题。')
    rationale: NonBlank = Field(description='整体审题结论及依据，用于解释通过、修订、重出或资料不足。')


def check_review(value):
    if value.checked_question_ids != ['essay-1', 'choice-1', 'blank-1']:
        raise ValueError('审题必须按固定顺序覆盖所有题目')
    if value.verdict == 'pass' and any(f.severity == 'blocking' for f in value.findings):
        raise ValueError('pass 不得携带阻断问题')
    if value.verdict in ('revise', 'regenerate') and not value.findings:
        raise ValueError('修订或重新出题必须记录具体问题')
    return value


class ReviewResult(Review):
    """审题包输出，额外校验覆盖三题、结论与问题清单的一致性。"""
    @model_validator(mode='after')
    def valid_review(self):
        return check_review(self)


class AwaitingReview(StrictModel):
    """更新题目后使用的待审标记，不能用于最终验收。"""
    phase: Literal['awaiting_review'] = Field(description='审题阶段：awaiting_review 待审；reviewed 已完成审题。')


class QuestionState(StrictModel):
    """贯穿审题与有限修订循环的完整状态；每一步接收并返回完整数据。"""
    document: Document = Field(description='读取块产出的完整文档，含文件名、正文与带行号正文；后续依据核验的固定来源。')
    plan: SufficientPlan = Field(description='已通过核验的三题规划；修订和重新出题仍使用同一规划。')
    current: Questions = Field(description='当前待审查或修订的完整三题，后续更新块整体替换它。')
    review: AwaitingReview | Review = Field(description='待审标记或最近一次完整审题结果；控制是否修订及采用何种修订路径。')
    revision_rounds: int = Field(ge=0, le=2, description='已经采纳的修订或重新出题轮数；初始为 0，最多 2 轮，审题本身不加轮。')


class GenerationInput(StrictModel):
    """准备出题块输出的上下文封装，统一初稿与重新出题入口。"""
    # 初稿与重新出题共用包，两个阶段都由 Python 准备主数据。
    context: SufficientPlan | QuestionState = Field(description='初稿时为已核验规划；重新出题时为含旧题及审题意见的完整状态。原文与规划另按顺序作为参考输入。')


class PlannerEntry(NodeInput[Document, tuple[()]]):
    """规划节点入口：主数据为完整原文，无参考输入。"""
    pass


class GeneratorEntry(NodeInput[GenerationInput, tuple[Document, SufficientPlan]]):
    """出题节点入口：主数据为上下文；参考依次为完整原文、核验后的规划。"""
    pass


class StateEntry(NodeInput[QuestionState, tuple[()]]):
    """审题和修订节点入口：主数据为完整题目状态，无参考输入。"""
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

from agent_platform.blocks import block

@block(id='question-needs-regeneration', version='3.0.0', name='是否需要重新出题', description='在已经要求修改的完整状态上区分重新出题与定向修订，返回严格布尔值。用于修订循环内的 if 条件；真走重新出题，假走定向修订。无参考输入。')
def run(value: NodeInput[QuestionState, tuple[()]]) -> bool:
    state = verify_state(value.primary)
    if not isinstance(state.review, Review) or state.review.verdict not in ('revise', 'regenerate'):
        quality_fail('分支条件要求修订或重新出题状态')
    return state.review.verdict == 'regenerate'
