"""paragraph-exact-v1：只规范文本，不做近似匹配或语义改写。"""
import re
import unicodedata
from pydantic import Field
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.errors import ErrorResponse, PlatformError
from .contracts import SimilarityInput, NonemptyText


class PreparedTexts(StrictModel):
    target_paragraphs: list[NonemptyText] = Field(min_length=1)
    comparison_paragraphs: list[list[NonemptyText]] = Field(min_length=1)


def paragraphs(text: str) -> list[str]:
    text = unicodedata.normalize('NFC', text.replace('\r\n', '\n').replace('\r', '\n'))
    return [clean for line in text.split('\n')
            if (clean := re.sub(r'[^\S\n]+', ' ', line).strip())]


def preprocess(value: SimilarityInput) -> PreparedTexts:
    target = paragraphs(value.target_text)
    comparisons = [paragraphs(text) for text in value.comparison_texts]
    for path, content in [(['targetText'], target), *[
        (['comparisonTexts', index], parts) for index, parts in enumerate(comparisons)
    ]]:
        if not content:
            raise PlatformError(ErrorResponse(
                code='CONTRACT_VALIDATION_ERROR', stage='similarity.preprocess',
                message='清洗后文本不得为空', field_path=path), 422)
    return PreparedTexts(target_paragraphs=target, comparison_paragraphs=comparisons)
