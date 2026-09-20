"""资源入口的唯一封装；只转换 JSON 数组容器，元素始终严格校验。"""
from typing import Annotated, Generic, TypeVar, get_origin, get_args
from pydantic import field_validator, ConfigDict
from .base import StrictModel

P = TypeVar('P')
R = TypeVar('R')


class NodeInput(StrictModel, Generic[P, R]):
    model_config = ConfigDict(json_schema_extra={'x-node-input-version': 1})

    primary: P
    references: R

    @field_validator('references', mode='before')
    @classmethod
    def json_array(cls, value):
        return tuple(value) if type(value) is list else value


def require_node_input(annotation):
    if not isinstance(annotation, type) or not issubclass(annotation, NodeInput):
        raise TypeError('资源入口必须声明 NodeInput[P, tuple[...]]；请升级资源版本')
    reference_type = annotation.model_fields['references'].annotation
    if get_origin(reference_type) is not tuple or Ellipsis in get_args(reference_type):
        raise TypeError('references 必须声明固定位置元组；零参考使用 tuple[()]')
    if set(annotation.model_fields) != {'primary', 'references'}:
        raise TypeError('节点入口只允许 primary 和 references')


def primary_annotation(model):
    """Pydantic 分离了 Annotated 元数据；导出业务端口时必须保留其约束。"""
    field = model.model_fields['primary']
    return Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation


def input_schemas(schema):
    """从资源公开 Schema 分解入口，编译器和表单不另写业务 Schema。"""
    from ..flows.compatibility import resolve, Incompatible
    root = schema
    schema = resolve(schema, root)
    properties = schema.get('properties', {})
    if schema.get('x-node-input-version') != 1 or set(properties) != {'primary', 'references'}:
        raise Incompatible('资源仍使用旧裸输入协议，请升级为 NodeInput 并重新加载')
    references = resolve(properties['references'], root)
    slots = references.get('prefixItems', [])
    if references.get('type') != 'array' or references.get('minItems', 0) != len(slots) or references.get('maxItems') != len(slots):
        raise Incompatible('参考输入必须为固定位置、固定数量的元组')
    def rooted(value):
        return {**value, '$defs': root.get('$defs', {})}
    return rooted(properties['primary']), [rooted(slot) for slot in slots]
