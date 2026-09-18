"""单文件块装饰器与严格类型适配。装饰不调用被注册函数。"""
from typing import get_args, get_origin, Annotated, Literal, Union
import types
from pydantic import BaseModel, TypeAdapter, JsonValue
from ..contracts.base import StrictModel
from ..contracts.packages import Identifier, Version
from pydantic import Field


class BlockMetadata(StrictModel):
    id: Identifier
    version: Version
    name: str = Field(min_length=1)
    description: str = ''
    dependencies: list[str] = Field(default_factory=list)
    uses_api: bool = False


def block(*, id, version, name, description='', dependencies=(), api=False):
    metadata = BlockMetadata(id=id, version=version, name=name, description=description,
                             dependencies=list(dependencies), uses_api=api)
    def register(function):
        function.__block_metadata__ = metadata
        return function
    return register


def strict_adapter(annotation):
    """拒绝宽松 BaseModel/Any/任意对象；嵌套模型同样需要严格声明。"""
    seen = set()
    def check(value):
        if value in seen:
            return
        seen.add(value)
        if value is JsonValue:
            return
        origin, args = get_origin(value), get_args(value)
        if origin is Annotated:
            check(args[0])
        elif origin is Literal:
            if not all(type(v) in (str, int, bool, float, type(None)) for v in args):
                raise TypeError('枚举值必须是 JSON 标量')
        elif origin in (list, dict, Union, types.UnionType):
            if origin is dict and args[0] is not str:
                raise TypeError('对象键必须是字符串')
            for item in args:
                check(item)
        elif isinstance(value, type) and issubclass(value, BaseModel):
            if not issubclass(value, StrictModel) or value.model_config.get('strict') is not True or value.model_config.get('extra') != 'forbid':
                raise TypeError('模型必须继承 StrictModel 并禁止额外字段')
            for field in value.model_fields.values():
                check(field.annotation)
        elif value not in (str, int, float, bool, type(None)):
            raise TypeError('契约必须使用严格 JSON 类型或 StrictModel')
    check(annotation)
    adapter = TypeAdapter(annotation)
    adapter.json_schema()
    return adapter
