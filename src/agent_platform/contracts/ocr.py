"""本地 OCR 模型组合与识别的权威契约。"""
from hashlib import sha256
import json
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .base import StrictModel
from .files import SHA256

OCRId = Annotated[str, Field(pattern=r'^ocr_[a-f0-9]{64}$')]


class OCRFile(StrictModel):
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


class OCRManifest(StrictModel):
    format_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=200)
    license: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=2000)
    adapter: Literal['rapidocr-onnx'] = 'rapidocr-onnx'
    adapter_version: Literal['1'] = '1'
    detection: OCRFile
    recognition: OCRFile
    classification: OCRFile
    dictionary: Literal['onnx-metadata'] = 'onnx-metadata'
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
        if len({self.detection.path, self.recognition.path, self.classification.path}) != 3:
            raise ValueError('检测、识别与方向分类必须是不同文件')
        return self

    def identity(self) -> str:
        canonical = json.dumps(self.model_dump(mode='json', by_alias=True),
                               ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return 'ocr_' + sha256(canonical.encode()).hexdigest()


class OCRSnapshot(StrictModel):
    model_id: OCRId
    manifest: OCRManifest

    @model_validator(mode='after')
    def verify_identity(self):
        if self.model_id != self.manifest.identity():
            raise ValueError('模型身份与清单内容不一致')
        return self


class OCRModel(OCRSnapshot):
    size_bytes: int = Field(gt=0)
    imported_at: str
    status: Literal['ready', 'unavailable']
    error: str | None = None


class OCRSelection(StrictModel):
    model_id: OCRId | None = None


class OCRRequest(StrictModel):
    # PNG 通过现有 JSON 子进程通道传递；不接受任意本机路径。
    image_base64: str = Field(min_length=1, max_length=12 * 1024 * 1024)
    use_classification: bool = False


class OCRPoint(StrictModel):
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)


class OCRLine(StrictModel):
    points: list[OCRPoint] = Field(min_length=4, max_length=4)
    text: str = Field(max_length=20000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class OCRResult(StrictModel):
    model_id: OCRId
    image_sha256: SHA256
    width: int = Field(ge=1, le=6000)
    height: int = Field(ge=1, le=6000)
    lines: list[OCRLine] = Field(max_length=5000)
    queue_seconds: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    inference_seconds: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def bounds(self):
        if self.width * self.height > 20000000:
            raise ValueError('图片超过 2000 万像素')
        if any(p.x > self.width or p.y > self.height for line in self.lines for p in line.points):
            raise ValueError('识别框超出图片范围')
        if sum(len(line.text) for line in self.lines) > 200000:
            raise ValueError('识别文字总量超限')
        return self


class OCRImport(StrictModel):
    directory: str = Field(min_length=1, max_length=4096)


class OCRDiagnostic(StrictModel):
    recognized_text: str = Field(min_length=1)
    load_seconds: float = Field(ge=0, allow_inf_nan=False)
    inference_seconds: float = Field(ge=0, allow_inf_nan=False)
    peak_memory_bytes: int = Field(gt=0)


class OCRJob(StrictModel):
    job_id: str
    status: Literal['running', 'completed', 'failed'] = 'running'
    progress: str
    model: OCRModel | None = None
    diagnostic: OCRDiagnostic | None = None
    error: str | None = None


class OCRRecord(StrictModel):
    node_id: str
    resource_digest: SHA256
    use_classification: bool
    result: OCRResult

