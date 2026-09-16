"""将 HTTP 边界异常转换为稳定、脱敏的错误对象。"""
from http import HTTPStatus
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from .contracts.errors import ErrorResponse, ErrorDetails, PlatformError

_REASONS = {
    'missing': '缺少必填字段', 'extra_forbidden': '不允许未知字段',
    'int_type': '必须为整数', 'float_type': '必须为数值',
    'string_type': '必须为字符串', 'bool_type': '必须为布尔值',
    'list_type': '必须为数组', 'model_type': '必须为对象',
    'json_invalid': 'JSON 格式无效',
}


def response(error: ErrorResponse, status: int) -> JSONResponse:
    return JSONResponse(error.model_dump(mode='json', by_alias=True), status_code=status)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        # 不使用 msg、input、ctx；自定义校验异常可能将密钥嵌入其中。
        return response(ErrorResponse(
            code='CONTRACT_VALIDATION_ERROR', stage='request.input',
            message=_REASONS.get(first['type'], '字段不符合契约约束'),
            field_path=list(first['loc']),
        ), 422)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError):
        return response(exc.error, exc.status_code)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return response(ErrorResponse(
            code='RECORD_NOT_FOUND' if exc.status_code == 404 else 'HTTP_ERROR',
            stage='http', message=HTTPStatus(exc.status_code).phrase,
            details=ErrorDetails(http_status=exc.status_code),
        ), exc.status_code)

    @app.exception_handler(ResponseValidationError)
    async def invalid_output(request: Request, exc: ResponseValidationError):
        return response(ErrorResponse(
            code='OUTPUT_VALIDATION_ERROR', stage='response.output',
            message='输出不符合契约约束', field_path=list(exc.errors()[0]['loc']),
        ), 500)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        return response(ErrorResponse(
            code='INTERNAL_ERROR', stage='application', message='内部执行失败',
        ), 500)
