"""编辑草稿允许未完成结构；发布前用 FlowDraft 做严格预检。"""
from pydantic import JsonValue, Field
from .base import StrictModel


class DraftWrite(StrictModel):
    content: dict[str, JsonValue] = Field(default_factory=dict)


class DraftDocument(DraftWrite):
    draft_id: str
