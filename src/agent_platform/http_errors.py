"""将 HTTP 边界异常转换为稳定、脱敏的错误对象。"""
from http import HTTPStatus
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from .contracts.errors import ErrorResponse, ErrorDetails, PlatformError



def response(error: ErrorResponse, status: int) -> JSONResponse:
    return JSONResponse(error.model_dump(mode='json', by_alias=True), status_code=status)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        from .validation_issues import validation_exception
        error = validation_exception(exc, stage='request.input')
        return response(error.error, error.status_code)

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
        from .validation_issues import validation_exception
        error = validation_exception(exc, stage='response.output', code='OUTPUT_VALIDATION_ERROR', status=500)
        return response(error.error, error.status_code)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        return response(ErrorResponse(
            code='INTERNAL_ERROR', stage='application', message='内部执行失败',
        ), 500)
