"""按目标段落出现位置计 Unicode 码点，不计段落间换行。"""
from collections import defaultdict
from .contracts import ParagraphMatch, QuantitativeItem, QuantitativeReport
from .preprocessing import PreparedTexts


def score(value: PreparedTexts) -> QuantitativeReport:
    total = sum(map(len, value.target_paragraphs))
    items = []
    for comparison_index, paragraphs in enumerate(value.comparison_paragraphs):
        positions = defaultdict(list)
        for index, paragraph in enumerate(paragraphs):
            positions[paragraph].append(index)
        matches, matched = [], 0
        for index, paragraph in enumerate(value.target_paragraphs):
            if paragraph in positions:
                matched += len(paragraph)
                matches.append(ParagraphMatch(target_paragraph_index=index,
                    comparison_paragraph_indices=positions[paragraph]))
        items.append(QuantitativeItem(comparison_index=comparison_index,
            similarity=matched / total, matched_target_characters=matched,
            total_target_characters=total, matches=matches))
    return QuantitativeReport(method='paragraph-exact-v1', items=items)
