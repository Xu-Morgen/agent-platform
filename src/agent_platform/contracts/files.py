"""平台文件引用；路径只存在于运行上下文，不进入业务输入。"""
from typing import Annotated, Literal
from pydantic import Field
from .base import StrictModel

SHA256 = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class FileReference(StrictModel):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')
    original_name: str = Field(min_length=1, max_length=255, pattern=r'^[^/\\\x00-\x1f]+$')
    format: Literal['pdf', 'docx']
    size: int = Field(gt=0)
    sha256: SHA256


# 明确标注驱动控件；不根据字段名称或业务名称猜测文件类型。
TaskFile = Annotated[FileReference, Field(json_schema_extra={
    'x-platform-file': {'formats': ['pdf', 'docx']},
})]
