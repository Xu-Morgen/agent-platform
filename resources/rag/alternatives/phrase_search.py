"""可替换检索基线：完整短语计数，不拆中文二元组。"""
from agent_platform.blocks import block
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.retrieval import ParsedCorpus, SearchResults


@block(id='rag-phrase-search', version='1.0.0', name='完整短语检索', description='替代词面检索：terms 为完整短语，留空时以整个 query 为短语；按命中短语数和次数排序。不拆词、不扩写；输入输出与默认检索兼容。')
def run(value: NodeInput[ParsedCorpus, tuple[()]]) -> SearchResults:
    corpus = value.primary
    terms = list(dict.fromkeys(term.strip().casefold() for term in
                 (corpus.selection.request.terms or [corpus.selection.request.query]) if term.strip()))[:100]
    candidates = []
    for item in corpus.fragments:
        counts = [min(item.text.casefold().count(term), 20) for term in terms]
        if any(counts):
            candidates.append(item.model_copy(update={'score': float(100 * sum(count > 0 for count in counts) + sum(counts))}))
    candidates.sort(key=lambda item: -item.score)
    return SearchResults(corpus=corpus, terms=terms, candidates=candidates,
                         algorithm='rag-phrase-search@1.0.0:whole-phrase-frequency')
