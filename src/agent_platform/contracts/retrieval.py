"""可选的标准检索数据契约；算法由普通资源实现，平台执行器不依赖它。"""
from typing import Literal
from pydantic import Field
from .base import StrictModel
from .knowledge import TaskKnowledge, FixedKnowledgeReference, DocumentVersion, Evidence, EvidenceRegistration


class RetrievalLimits(StrictModel):
    max_documents: int = Field(default=20, ge=1, le=200)
    max_file_bytes: int = Field(default=10485760, ge=1, le=52428800)
    max_characters: int = Field(default=200000, ge=100, le=1000000)
    max_fragments: int = Field(default=300, ge=1, le=500)
    fragment_characters: int = Field(default=1200, ge=100, le=20000)
    top_k: int = Field(default=8, ge=1, le=100)
    context_characters: int = Field(default=12000, ge=100, le=100000)


class RetrievalRequest(StrictModel):
    knowledge: TaskKnowledge
    query: str = Field(min_length=1, max_length=10000)
    terms: list[str] = Field(default_factory=list, max_length=30, description='可选检索词；留空按中文二元组和英文词生成。')
    limits: RetrievalLimits = Field(default_factory=RetrievalLimits)


class DocumentSelection(StrictModel):
    request: RetrievalRequest
    reference: FixedKnowledgeReference
    documents: list[DocumentVersion] = Field(max_length=200)
    total_documents: int = Field(ge=0)
    scope_limited: bool


class ParsedCorpus(StrictModel):
    selection: DocumentSelection
    scanned_versions: list[str] = Field(max_length=200)
    fragments: list[Evidence] = Field(max_length=500)
    scope_limited: bool


class SearchResults(StrictModel):
    corpus: ParsedCorpus
    terms: list[str] = Field(max_length=100)
    candidates: list[Evidence] = Field(max_length=500)
    algorithm: str


class EvidenceContext(StrictModel):
    evidence: EvidenceRegistration
    terms: list[str] = Field(max_length=100)
    algorithm: str
    context_limited: bool


class Citation(StrictModel):
    fragment_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=20000)


class GroundedAnswer(StrictModel):
    status: Literal['answered', 'insufficient_source']
    answer: str = Field(min_length=1, max_length=20000)
    citations: list[Citation] = Field(max_length=100)

    def citations_required(self):
        if self.status == 'answered' and not self.citations:
            raise ValueError('回答必须带有选用证据引用')
        if self.status == 'insufficient_source' and self.citations:
            raise ValueError('资料不足结果不应声明已回答引用')
        return self


class VerifiedAnswer(StrictModel):
    result: GroundedAnswer
    context: EvidenceContext
    citation_check: Literal['passed'] = 'passed'


class DocumentPreviewRequest(StrictModel):
    knowledge: TaskKnowledge
    version_id: str = Field(pattern=r'^dv_[a-f0-9]{32}$')
    limits: RetrievalLimits = Field(default_factory=RetrievalLimits)


class DocumentPreviewService(StrictModel):
    service_id: str
    instance_id: str
    name: str
    version: str
