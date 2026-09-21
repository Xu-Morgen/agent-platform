"""词面基线：中文二元组/英文词，显式词可覆盖查询拆分；按覆盖率和频次评分。"""
import re
from agent_platform.blocks import block
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.retrieval import ParsedCorpus, SearchResults


@block(id='rag-lexical-search', version='1.0.0', name='词面检索', description='显式检索词优先；否则中文二元组与英文词。评分=命中词覆盖率×100+各词频次（每词最多5次）；同分按原文顺序。无参考输入。')
def run(value: NodeInput[ParsedCorpus, tuple[()]]) -> SearchResults:
    corpus = value.primary
    explicit = corpus.selection.request.terms
    tokens = []
    if explicit:
        tokens = [term.strip().casefold() for term in explicit if term.strip()]
    else:
        for part in re.findall(r'[\u3400-\u9fff]+|[a-zA-Z0-9]+', corpus.selection.request.query.casefold()):
            tokens.extend([part] if len(part) < 2 or part.isascii() else [part[i:i+2] for i in range(len(part)-1)])
    terms = list(dict.fromkeys(tokens))[:100]
    candidates = []
    for item in corpus.fragments:
        text = item.text.casefold()
        counts = [min(text.count(term), 5) for term in terms]
        if any(counts):
            score = 100.0 * sum(count > 0 for count in counts) / len(terms) + sum(counts)
            candidates.append(item.model_copy(update={'score': score}))
    candidates.sort(key=lambda item: -item.score)
    return SearchResults(corpus=corpus, terms=terms, candidates=candidates, algorithm='rag-lexical-search@1.0.0:coverage-frequency')
