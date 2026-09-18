"""可公开错误契约；上游异常文本与响应不进入错误对象。"""
from typing import Literal
from pydantic import Field
from .base import StrictModel

ErrorCode = Literal[
    'LOOP_ITERATION_LIMIT', 'RUN_CANCELLED', 'GRAPH_EXECUTION_LIMIT', 'RESULT_NOT_READY', 'CONFIGURATION_ERROR', 'CONTRACT_VALIDATION_ERROR', 'DEPENDENCY_ERROR',
    'ENVIRONMENT_IN_USE', 'LOOP_BUDGET_EXCEEDED', 'TOKEN_BUDGET_EXCEEDED',
    'TOKEN_ACCOUNTING_UNSUPPORTED', 'MODEL_TIMEOUT', 'MODEL_TRANSPORT_ERROR',
    'API_TIMEOUT', 'API_TRANSPORT_ERROR', 'OUTPUT_VALIDATION_ERROR',
    'RECORD_NOT_FOUND', 'VERSION_CONFLICT', 'INTERNAL_ERROR', 'HTTP_ERROR',
    'BACKEND_UNAVAILABLE', 'STARTUP_ERROR', 'APPLICATION_EXIT',
]


class ValidationIssue(StrictModel):
    code: str = 'CONTRACT_VALIDATION_ERROR'
    stage: str = 'flow.validation'
    reason: str
    reason_type: str = 'constraint'
    expected: str | None = None
    field_path: list[str | int] = Field(default_factory=list)
    node_id: str | None = None
    source_node_id: str | None = None
    source_port: list[str | int] | None = None
    target_port: list[str | int] | None = None


class ErrorDetails(StrictModel):
    """仅允许已知非敏感元数据，不能附带任意上游字典。"""
    run_status: Literal['queued', 'running', 'completed', 'failed', 'cancelled'] | None = None
    package_binding_id: str | None = None
    attempt: int | None = Field(default=None, ge=1)
    active_run_ids: list[str] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None, gt=0)
    http_status: int | None = Field(default=None, ge=100, le=599)


class ErrorResponse(StrictModel):
    code: ErrorCode
    stage: str
    message: str
    run_id: str | None = None
    field_path: list[str | int] | None = None
    node_id: str | None = None
    source_node_id: str | None = None
    source_port: list[str | int] | None = None
    target_port: list[str | int] | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    details: ErrorDetails = Field(default_factory=ErrorDetails)


class PlatformError(Exception):
    def __init__(self, error: ErrorResponse, status_code: int = 400):
        super().__init__(error.message)
        self.error = error
        self.status_code = status_code


def upstream_error(kind: Literal['model', 'api'], *, timeout: bool = False) -> PlatformError:
    """不接收原始上游内容，从而避免凭据混入可公开错误。"""
    code = f'{kind.upper()}_{"TIMEOUT" if timeout else "TRANSPORT_ERROR"}'
    return PlatformError(ErrorResponse(
        code=code, stage=f'{kind}.transport',
        message='上游请求超时' if timeout else '上游连接失败',
    ), status_code=504 if timeout else 502)
