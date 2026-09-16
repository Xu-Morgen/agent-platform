"""本地实例定义挂载；同名再次加载返回独立句柄，保留旧内容。"""
from dataclasses import dataclass
from uuid import uuid4
from pydantic import ValidationError
from ..contracts.instances import InstanceDefinition
from .snapshots import capture
from .validation import invalid, load_symbol, validation_error


@dataclass(frozen=True)
class LoadedDefinition:
    load_id: str
    definition_json: str
    content: object

    @property
    def definition(self):
        return InstanceDefinition.model_validate_json(self.definition_json)


class DefinitionRegistry:
    def __init__(self):
        self._items = {}

    def load(self, directory):
        content = capture(directory)
        try:
            definition = InstanceDefinition.model_validate_json(content.read_resource('instance.json'))
            for key in ('entry', 'workflow', 'input_model', 'output_model'):
                load_symbol(content, getattr(definition, key), [key], model=key.endswith('_model'))
            # 保留 budget 中实际提供的字段，让组合校验器显式生成缺省预算。
            value = LoadedDefinition('def_' + uuid4().hex, definition.model_dump_json(by_alias=True, exclude_unset=True), content)
            self._items[value.load_id] = value
            return value
        except ValidationError as exc:
            content.close()
            raise validation_error(exc) from None
        except Exception:
            content.close()
            raise

    def get(self, load_id):
        if load_id not in self._items:
            raise invalid('实例定义未加载', ['definitionLoadId'], code='DEPENDENCY_ERROR')
        return self._items[load_id]
