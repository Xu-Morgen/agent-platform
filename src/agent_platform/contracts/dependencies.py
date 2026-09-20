"""仅声明数据的依赖来源与模型文件；禁止安装脚本和带凭据地址。"""
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit, unquote
from packaging.requirements import Requirement, InvalidRequirement
from packaging.utils import canonicalize_name
from pydantic import Field, field_validator, model_validator
from .base import StrictModel
from .files import SHA256


def public_https(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != 'https' or not url.hostname or url.username is not None
            or url.password is not None or url.query or url.fragment
            or any(c.isspace() for c in value)):
        raise ValueError('首期下载地址必须是无凭据、无查询参数的固定 HTTPS URL')
    return value


class IndexSource(StrictModel):
    kind: Literal['index']
    url: str

    _url = field_validator('url')(public_https)


class WheelSource(StrictModel):
    kind: Literal['wheel']
    package: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    url: str
    sha256: SHA256

    @field_validator('url')
    @classmethod
    def wheel_url(cls, value):
        public_https(value)
        if not unquote(urlsplit(value).path).endswith('.whl'):
            raise ValueError('直接依赖下载只支持 wheel')
        return value


DependencySource = Annotated[IndexSource | WheelSource, Field(discriminator='kind')]


class ModelFile(StrictModel):
    name: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    version: str = Field(min_length=1, max_length=100)
    url: str
    sha256: SHA256
    filename: str = Field(min_length=1, max_length=255)

    _url = field_validator('url')(public_https)

    @field_validator('filename')
    @classmethod
    def safe_filename(cls, value):
        if (value in ('.', '..') or PurePosixPath(value).name != value
                or '\\' in value or any(ord(c) < 32 for c in value)):
            raise ValueError('模型目标文件名必须是单个文件名')
        return value


class RuntimeDeclaration(StrictModel):
    dependencies: list[str] = Field(default_factory=list)
    dependency_sources: list[DependencySource] = Field(default_factory=list)
    models: list[ModelFile] = Field(default_factory=list)

    @field_validator('dependencies')
    @classmethod
    def requirements(cls, values):
        names = set()
        for value in values:
            try:
                requirement = Requirement(value)
            except InvalidRequirement:
                raise ValueError('依赖必须是合法的 PEP 508 包版本声明') from None
            if requirement.url or not requirement.specifier:
                raise ValueError('依赖须声明版本范围；下载地址请使用 dependencySources')
            name = canonicalize_name(requirement.name)
            if name in names:
                raise ValueError('依赖包名称不能重复')
            names.add(name)
        return values

    @model_validator(mode='after')
    def unique_sources(self):
        indexes = [s for s in self.dependency_sources if s.kind == 'index']
        wheels = [canonicalize_name(s.package) for s in self.dependency_sources if s.kind == 'wheel']
        names = [m.name for m in self.models]
        if len(indexes) > 1 or len(wheels) != len(set(wheels)) or len(names) != len(set(names)):
            raise ValueError('只允许一个索引源；wheel 包名和模型名称不能重复')
        declared = {canonicalize_name(Requirement(r).name) for r in self.dependencies}
        if not set(wheels) <= declared:
            raise ValueError('wheel 来源必须对应 dependencies 中声明的包')
        return self
