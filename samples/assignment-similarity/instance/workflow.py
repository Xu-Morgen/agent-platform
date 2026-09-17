"""所有对照一次送入语义包；最终报告仅在两类结果都成功后组装。"""
from agent_platform.runtime.context import current_context
from agent_platform.runtime.graphs import build_sequential
from .contracts import SimilarityInput, QualitativeReport, validate_report
from .models import State
from .preprocessing import preprocess
from .scoring import score


def clean(state):
    return {'prepared': preprocess(SimilarityInput(
        target_text=state.target_text, comparison_texts=state.comparison_texts))}


def quantitative(state):
    return {'quantitative': score(state.prepared)}


async def semantic(state):
    prepared = state.prepared
    result = await current_context.get().invoke_package('semantic', {
        'targetText': '\n'.join(prepared.target_paragraphs),
        'comparisonTexts': ['\n'.join(parts) for parts in prepared.comparison_paragraphs],
    })
    return {'qualitative': QualitativeReport.model_validate(result.model_dump(by_alias=True),
        context={'comparison_count': len(state.comparison_texts)})}


def assemble(state):
    request = SimilarityInput(target_text=state.target_text, comparison_texts=state.comparison_texts)
    report = validate_report({'quantitative':state.quantitative, 'qualitative':state.qualitative}, request)
    return {'report':report}


def build_graph():
    return build_sequential(State, [('clean', clean), ('quantitative', quantitative),
                                    ('semantic', semantic), ('assemble', assemble)])
