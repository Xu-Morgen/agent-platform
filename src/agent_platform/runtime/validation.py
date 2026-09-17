"""运行时契约检查，保留阶段与字段路径而不泄露输入。"""
from pydantic import BaseModel, ValidationError
from ..contracts.errors import ErrorResponse, PlatformError


def validate(model, value, stage):
    if isinstance(value, BaseModel):
        value = value.model_dump(by_alias=True)
    try:
        return model.model_validate(value, strict=True)
    except ValidationError as exc:
        from ..validation_issues import validation_exception
        raise validation_exception(exc, stage=stage, code='OUTPUT_VALIDATION_ERROR' if stage.endswith('output') else 'CONTRACT_VALIDATION_ERROR') from None
