"""同一模型同时负责运行时校验及公开 JSON Schema。"""
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class StrictModel(BaseModel):
    """嵌套契约也应继承此类；不接受未知字段或隐式类型转换。"""

    model_config = ConfigDict(
        strict=True,
        extra='forbid',
        alias_generator=to_camel,
        populate_by_name=True,
        validate_default=True,
        validate_assignment=True,
        revalidate_instances='always',
    )


def export_schema(model: type[StrictModel]) -> dict[str, Any]:
    return model.model_json_schema(by_alias=True, mode='validation')
