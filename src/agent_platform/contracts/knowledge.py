"""知识库标准引用和受控读取协议；业务数据不携带私有存储路径。"""
from typing import Annotated, Literal
from pydantic import Field, JsonValue
from .base import StrictModel
from .files import SHA256

KnowledgeId = Annotated[str, Field(pattern=r'^kb_[a-f0-9]{32}$')]
RevisionId = Annotated[str, Field(pattern=r'^kr_[a-f0-9]{32}$')]
DocumentId = Annotated[str, Field(pattern=r'^doc_[a-f0-9]{32}$')]
VersionId = Annotated[str, Field(pattern=r'^dv_[a-f0-9]{32}$')]


class KnowledgeReference(StrictModel):
    knowledge_id: KnowledgeId
    revision_id: RevisionId | None = None


TaskKnowledge = Annotated[KnowledgeReference, Field(json_schema_extra={'x-platform-knowledge': True})]


class FixedKnowledgeReference(KnowledgeReference):
    revision_id: RevisionId


class KnowledgeWrite(StrictModel):
    name: str = Field(min_length=1, max_length=200)


class KnowledgeUpdate(KnowledgeWrite):
    archived: bool = False


class KnowledgeBase(StrictModel):
    knowledge_id: KnowledgeId
    name: str = Field(min_length=1, max_length=200)
    revision_id: RevisionId
    archived: bool = False
    created_at: str


class DocumentVersion(StrictModel):
    document_id: DocumentId
    version_id: VersionId
    original_name: str = Field(min_length=1, max_length=255)
    format: Literal['pdf', 'docx'] = 'docx'
    size: int = Field(gt=0)
    sha256: SHA256
    created_at: str


class KnowledgeRevision(FixedKnowledgeReference):
    versions: list[VersionId]
    created_at: str


class KnowledgePageRequest(StrictModel):
    reference: FixedKnowledgeReference
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class KnowledgePage(StrictModel):
    reference: FixedKnowledgeReference
    items: list[DocumentVersion] = Field(max_length=200)
    total: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=0)


class DocumentReadRequest(StrictModel):
    reference: FixedKnowledgeReference
    version_id: VersionId
    max_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)


class Evidence(StrictModel):
    reference: FixedKnowledgeReference
    document_id: DocumentId
    version_id: VersionId
    fragment_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20000)
    sha256: SHA256
    locator: str = Field(min_length=1, max_length=300)
    reader: str = Field(min_length=1, max_length=300)
    score: float = 0.0

    def verify_digest(self):
        from hashlib import sha256
        if sha256(self.text.encode()).hexdigest() != self.sha256:
            raise ValueError('证据摘要与正文不一致')
        return self


class EvidenceRegistration(StrictModel):
    query: str = Field(max_length=10000)
    reference: FixedKnowledgeReference
    scanned_versions: list[VersionId] = Field(max_length=1000)
    scope_limited: bool
    candidates: list[Evidence] = Field(max_length=500)
    selected: list[Evidence] = Field(max_length=100)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

    def verify_selection(self):
        import json
        if len(json.dumps(self.parameters, ensure_ascii=False).encode()) > 65536:
            raise ValueError('证据参数超过 64 KiB 上限')
        if len(set(self.scanned_versions)) != len(self.scanned_versions):
            raise ValueError('扫描版本标识重复')
        candidates = {item.fragment_id: item for item in self.candidates}
        if len(candidates) != len(self.candidates):
            raise ValueError('候选片段标识重复')
        if len({item.fragment_id for item in self.selected}) != len(self.selected):
            raise ValueError('选用片段标识重复')
        for item in self.candidates:
            item.verify_digest()
            if item.reference != self.reference or item.version_id not in self.scanned_versions:
                raise ValueError('证据不属于本次扫描范围')
        for item in self.selected:
            if candidates.get(item.fragment_id) != item:
                raise ValueError('选用证据必须与候选证据完全一致')
        if sum(len(item.text) for item in self.candidates) > 1000000:
            raise ValueError('候选证据正文总量超过上限')
        return self


class EvidenceRecord(EvidenceRegistration):
    record_id: str
    node_id: str
    resource_digest: SHA256
