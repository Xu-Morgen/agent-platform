"""受信任本地声明的契约与错误检查。"""
from pydantic import ValidationError
from ..contracts.base import StrictModel
from ..contracts.errors import ErrorResponse, PlatformError


def invalid(message, path, *, code='CONFIGURATION_ERROR'):
    status = 404 if code == 'RECORD_NOT_FOUND' else 409 if code == 'VERSION_CONFLICT' else 422
    return PlatformError(ErrorResponse(code=code, stage='configuration', message=message, field_path=path), status)


def validation_error(exc: ValidationError, prefix=()):
    return invalid('字段不符合契约约束', [*prefix, *exc.errors()[0]['loc']])


def load_symbol(content, reference, path, *, model=False):
    try:
        symbol = content.load(reference)
        if model:
            if not isinstance(symbol, type) or not issubclass(symbol, StrictModel):
                raise TypeError()
            symbol.model_json_schema()
        elif not callable(symbol):
            raise TypeError()
        return symbol
    except Exception:
        raise invalid('入口或契约不可用，请检查声明和本地依赖', path, code='DEPENDENCY_ERROR') from None
