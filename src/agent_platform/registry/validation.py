"""受信任本地声明的契约与错误检查。"""
from pydantic import ValidationError
from ..contracts.base import StrictModel
from ..contracts.errors import ErrorResponse, PlatformError


def invalid(message, path, *, code='CONFIGURATION_ERROR'):
    status = 404 if code == 'RECORD_NOT_FOUND' else 409 if code == 'VERSION_CONFLICT' else 422
    return PlatformError(ErrorResponse(code=code, stage='configuration', message=message, field_path=path), status)


def validation_error(exc: ValidationError, prefix=()):
    from ..validation_issues import validation_exception
    return validation_exception(exc, prefix=prefix, code='CONFIGURATION_ERROR')


def load_model(content, reference, path):
    try:
        symbol = content.load(reference)
        if not isinstance(symbol, type) or not issubclass(symbol, StrictModel):
            raise TypeError()
        symbol.model_json_schema()
        return symbol
    except ModuleNotFoundError as exc:
        raise invalid(f'缺少代码依赖模块：{exc.name}', path, code='DEPENDENCY_ERROR') from None
    except SyntaxError as exc:
        raise invalid(f'已读取契约文件，但 Python 语法错误（第 {exc.lineno or "未知"} 行）', path) from None
    except Exception:
        raise invalid('契约不可用，请检查模型声明', path, code='DEPENDENCY_ERROR') from None
