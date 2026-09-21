"""平台设置的持久化与公开接口契约。"""
from typing import Annotated
from pydantic import Field
from .base import StrictModel

RunConcurrency = Annotated[int, Field(ge=1, le=64)]


class PlatformSettingsWrite(StrictModel):
    run_concurrency: RunConcurrency


class PlatformSettings(PlatformSettingsWrite):
    run_concurrency: RunConcurrency = 4


class PlatformSettingsView(PlatformSettings):
    active_run_concurrency: RunConcurrency
    restart_required: bool
    persistent: bool
