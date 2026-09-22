"""本地语义检索的权威数据契约；不包含向量或任意模型代码。"""
from hashlib import sha256
import json
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .base import StrictModel
from .files import SHA256
from .knowledge import Evidence, FixedKnowledgeReference

EmbeddingId = Annotated[str, Field(pattern=r'^emb_[a-f0-9]{64}$')]


class EmbeddingFile(StrictModel):
    path: str = Field(min_length=1, max_length=255)
    sha256: SHA256

    @field_validator('path')
    @classmethod
    def relative_file(cls, value):
        path = PurePosixPath(value)
        if (path.is_absolute() or '..' in path.parts or str(path) != value
                or value == '.' or '\\' in value or ':' in value
                or any(ord(c) < 32 for c in value)):
            raise ValueError('模型文件必须使用规范的目录内相对路径')
        return value


class EmbeddingManifest(StrictModel):
    format_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=200)
    license: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=2000)
    adapter: Literal['bert-onnx'] = 'bert-onnx'
    adapter_version: Literal['1'] = '1'
    weights: EmbeddingFile
    tokenizer: EmbeddingFile
    configuration: EmbeddingFile
    dimensions: int = Field(ge=1, le=4096)
    max_tokens: int = Field(ge=8, le=8192)
    pooling: Literal['cls', 'mean']
    normalize: Literal[True] = True
    document_instruction: str = Field(default='', max_length=1000)
    query_instruction: str = Field(default='', max_length=1000)
    precision: Literal['float32'] = 'float32'
    # 仅用于核对平台已安装的固定依赖，导入不会安装清单中的依赖。
    runtime: dict[str, str] = Field(min_length=1, max_length=30)
    python: str = Field(min_length=1, max_length=100)
    platform: Literal['linux-x86_64'] = 'linux-x86_64'

    @field_validator('runtime')
    @classmethod
    def pinned_runtime(cls, value):
        from packaging.utils import canonicalize_name
        from packaging.version import Version, InvalidVersion
        for name, version in value.items():
            if canonicalize_name(name) != name:
                raise ValueError('运行依赖名称必须规范化')
            try:
                Version(version)
            except InvalidVersion:
                raise ValueError('运行依赖必须声明精确版本') from None
        return value

    @field_validator('python')
    @classmethod
    def python_specifier(cls, value):
        from packaging.specifiers import SpecifierSet
        if not SpecifierSet(value):
            raise ValueError('必须声明 Python 兼容范围')
        return value

    @model_validator(mode='after')
    def distinct_files(self):
        if len({self.weights.path, self.tokenizer.path, self.configuration.path}) != 3:
            raise ValueError('权重、tokenizer 与配置必须是不同文件')
        return self

    def identity(self) -> str:
        canonical = json.dumps(self.model_dump(mode='json', by_alias=True),
                               ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return 'emb_' + sha256(canonical.encode()).hexdigest()


class EmbeddingSnapshot(StrictModel):
    model_id: EmbeddingId
    manifest: EmbeddingManifest

    @model_validator(mode='after')
    def verify_identity(self):
        if self.model_id != self.manifest.identity():
            raise ValueError('模型身份与清单内容不一致')
        return self


class EmbeddingModel(EmbeddingSnapshot):
    size_bytes: int = Field(gt=0)
    imported_at: str
    status: Literal['ready', 'unavailable']
    error: str | None = None


class EmbeddingSelection(StrictModel):
    model_id: EmbeddingId | None = None


class SemanticSearchRequest(StrictModel):
    reference: FixedKnowledgeReference
    query: str = Field(min_length=1, max_length=10000)
    fragments: list[Evidence] = Field(max_length=500)
    splitter: str = Field(min_length=1, max_length=300)
    scope_limited: bool
    top_k: int = Field(default=8, ge=1, le=100)
    minimum_score: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)

    @model_validator(mode='after')
    def verify_fragments(self):
        if not self.query.strip():
            raise ValueError('查询不能为空白文本')
        if len({item.fragment_id for item in self.fragments}) != len(self.fragments):
            raise ValueError('片段 ID 不得重复')
        if sum(len(item.text) for item in self.fragments) > 1000000:
            raise ValueError('片段正文总量超过一百万字符')
        for item in self.fragments:
            item.verify_digest()
            if item.reference != self.reference:
                raise ValueError('片段必须属于请求的固定知识库修订')
        return self


class SemanticSearchStats(StrictModel):
    document_tokens: int = Field(ge=0)
    query_tokens: int = Field(ge=0)
    encoded_fragments: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    batches: int = Field(ge=0)
    queue_seconds: float = Field(ge=0, allow_inf_nan=False)
    inference_seconds: float = Field(ge=0, allow_inf_nan=False)


class SemanticSearchResult(StrictModel):
    reference: FixedKnowledgeReference
    model: EmbeddingSnapshot
    algorithm: Literal['cosine-exact-v1'] = 'cosine-exact-v1'
    splitter: str = Field(min_length=1, max_length=300)
    scope_limited: bool
    candidates: list[Evidence] = Field(max_length=100)
    stats: SemanticSearchStats

    @model_validator(mode='after')
    def verify_candidates(self):
        import math
        previous = float('inf')
        seen = set()
        for item in self.candidates:
            item.verify_digest()
            if (item.reference != self.reference or item.fragment_id in seen
                    or not math.isfinite(item.score) or not -1 <= item.score <= 1
                    or item.score > previous):
                raise ValueError('候选范围、标识或余弦分数排序无效')
            seen.add(item.fragment_id)
            previous = item.score
        return self


class EmbeddingImport(StrictModel):
    directory: str = Field(min_length=1, max_length=4096)


class EmbeddingDiagnostic(StrictModel):
    dimensions: int = Field(ge=1, le=4096)
    finite: Literal[True]
    tokens: int = Field(ge=0)
    load_seconds: float = Field(ge=0, allow_inf_nan=False)
    inference_seconds: float = Field(ge=0, allow_inf_nan=False)
    peak_memory_bytes: int = Field(gt=0)


class EmbeddingJob(StrictModel):
    job_id: str
    status: Literal['running', 'completed', 'failed'] = 'running'
    progress: str
    model: EmbeddingModel | None = None
    diagnostic: EmbeddingDiagnostic | None = None
    error: str | None = None

class SemanticSearchRecord(StrictModel):
    node_id: str
    resource_digest: SHA256
    query: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(ge=1, le=100)
    minimum_score: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    result: SemanticSearchResult
