"""完整实例快照：声明和配置序列化，源码与资源使用只读字节映射。"""
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from uuid import uuid4
from ..configuration import validate_combination
from ..contracts.instances import InstanceDefinition
from ..registry.validation import invalid, load_symbol
from ..runtime.graphs import SequentialExecutor


@dataclass(frozen=True)
class InstanceSnapshot:
    instance_id: str
    definition_json: str
    content: object
    packages: object
    blocks: object
    configuration_json: str
    schema_json: str
    content_digest: str
    graph: SequentialExecutor

    @property
    def definition(self):
        return InstanceDefinition.model_validate_json(self.definition_json)

    @property
    def configuration(self):
        return json.loads(self.configuration_json)

    @property
    def schema(self):
        return json.loads(self.schema_json)


def prepare_snapshot(definition, content, packages, blocks, environments):
    definition, package_artifacts, block_artifacts, scopes, defaults = validate_combination(
        definition, content, packages, blocks, environments)
    load_symbol(content, definition.entry, ['entry'])
    factory = load_symbol(content, definition.workflow, ['workflow'])
    input_model = load_symbol(content, definition.input_model, ['inputModel'], model=True)
    output_model = load_symbol(content, definition.output_model, ['outputModel'], model=True)
    try:
        graph = factory()
        if not isinstance(graph, SequentialExecutor) or graph.graph.checkpointer is not None:
            raise TypeError()
    except Exception:
        raise invalid('图构造失败，须返回无持久化的 SequentialExecutor', ['workflow']) from None
    definition_json = definition.model_dump_json(by_alias=True)
    configuration_json = json.dumps(scopes, sort_keys=True, ensure_ascii=False)
    identity = {
        'definition': json.loads(definition_json), 'content': content.digest,
        'packages': {key: value.content.digest for key, value in package_artifacts.items()},
        'blocks': {'.'.join(key): value.content.digest for key, value in block_artifacts.items()},
        'configuration': scopes,
    }
    digest = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return InstanceSnapshot('ins_' + uuid4().hex, definition_json, content,
                            MappingProxyType(dict(package_artifacts)), MappingProxyType(dict(block_artifacts)),
                            configuration_json, json.dumps({'input': input_model.model_json_schema(),
                            'output': output_model.model_json_schema(), 'examples': []}), digest, graph)


class SnapshotRepository:
    def __init__(self):
        self._items = {}

    def save(self, definition, content, packages, blocks, environments):
        snapshot = prepare_snapshot(definition, content, packages, blocks, environments)
        self.add(snapshot)
        return snapshot

    def add(self, snapshot):
        if snapshot.instance_id in self._items:
            raise invalid('实例标识已存在', ['instanceId'], code='VERSION_CONFLICT')
        self._items[snapshot.instance_id] = snapshot

    def get(self, instance_id):
        if instance_id not in self._items:
            raise invalid('实例不存在', ['instanceId'], code='RECORD_NOT_FOUND')
        return self._items[instance_id]
