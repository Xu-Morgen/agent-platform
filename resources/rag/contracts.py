"""独立契约入口；按类名加载，SDK 中只有数据定义，不包含检索算法。"""
from agent_platform.contracts.retrieval import (
    RetrievalRequest, DocumentSelection, ParsedCorpus, SearchResults,
    EvidenceContext, GroundedAnswer, VerifiedAnswer,
)
