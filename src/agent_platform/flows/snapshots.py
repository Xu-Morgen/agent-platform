"""完整拼图快照；保存阶段不执行模块，内容来自已捕获的内存字节。"""
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from uuid import uuid4
from ..contracts.flows import FlowDraft, ModuleNode, ServiceNode, NodeConfiguration, walk_nodes
from ..contracts.errors import ErrorResponse, PlatformError
from ..registry.catalog import ModuleCatalog
from .configuration import NodeValidationRequest, validate_node
from .drafts import preflight
from .execution import compile_flow, COMPILER_VERSION


@dataclass(frozen=True)
class FlowSnapshot:
    instance_id: str
    draft_json: str
    catalog: object
    packages: object
    configuration_json: str
    schema_json: str
    content_digest: str
    graph: object
    compiler_version: str = COMPILER_VERSION

    @property
    def draft(self):
        return FlowDraft.model_validate_json(self.draft_json)

    @property
    def configuration(self):
        return json.loads(self.configuration_json)

    @property
    def schema(self):
        return json.loads(self.schema_json)

    @property
    def children(self):
        return {node.node_id: self.catalog.service(node) for node, _ in walk_nodes(self.draft.flow)
                if isinstance(node, ServiceNode)}

    def scopes(self, prefix=''):
        yield prefix, self
        for key, child in self.children.items():
            yield from child.scopes(prefix + key + '/')

    @property
    def all_packages(self):
        return {prefix + key: scope.draft.node_configurations[key]
                for prefix, scope in self.scopes() for key in scope.packages}


def prepare_flow_snapshot(draft, catalog, environments):
    result = preflight(draft.model_dump(by_alias=True), catalog, environments)
    if not result.valid:
        raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='flow.save', message='拼图预检失败', issues=result.issues))
    draft = draft.model_copy(deep=True)
    for node, _ in walk_nodes(draft.flow):
        if isinstance(node, ModuleNode) and node.kind == 'package':
            draft.node_configurations[node.node_id] = validate_node(
                NodeValidationRequest(node=node, configuration=draft.node_configurations[node.node_id]),
                catalog, environments).configuration
    return compile_snapshot(draft, catalog)


def compile_snapshot(draft, catalog, *, include_runtime_identity=True):
    """从已规范化的不可变草稿重建；恢复不依赖当前环境是否仍可调用。"""
    resources = set()
    contracts = {draft.input_contract, draft.output_contract}
    packages = {}
    children = {}
    for node, _ in walk_nodes(draft.flow):
        if isinstance(node, ModuleNode):
            resources.add(node.artifact_ref)
            if node.kind == 'package':
                packages[node.node_id] = catalog.artifact(node.artifact_ref)
        elif isinstance(node, ServiceNode):
            children[(node.service_id, node.instance_id)] = catalog.service(node)
        elif node.kind == 'if':
            contracts.add(node.output_contract)
        else:
            contracts.add(node.carry.contract)
    for ref in resources:
        view = catalog.get(ref)
        contracts.update(filter(None, [view.input_contract, view.primary_contract, view.output_contract, view.configuration_contract]))
    frozen = ModuleCatalog(None)
    frozen._views = MappingProxyType({r: catalog.get(r) for r in resources})
    frozen._artifacts = MappingProxyType({r: catalog.artifact(r) for r in resources})
    frozen._contracts = MappingProxyType({r: catalog.contract(r) for r in contracts})
    # 契约类型保留其内存模块来源；模块内容均由 ContentSnapshot 固定。
    frozen._contents = tuple(catalog._contents)
    def resolve_child(node):
        from ..registry.validation import invalid
        child = children.get((node.service_id, node.instance_id))
        if child is None:
            raise invalid('固定子服务实例不存在', ['instanceId'], code='DEPENDENCY_ERROR')
        return child
    frozen.service_resolver = resolve_child
    configuration = {'packages.' + key: c.parameters for key, c in draft.node_configurations.items() if isinstance(c, NodeConfiguration)}
    graph = compile_flow(draft, frozen)
    schema = {'input': frozen.contract(draft.input_contract).schema,
              'output': frozen.contract(draft.output_contract).schema,
              'examples': [e.model_dump(mode='json', by_alias=True) for e in draft.examples]}
    identity = {'draft': draft.model_dump(mode='json', by_alias=True), 'compiler': COMPILER_VERSION,
                'resources': {r: frozen.get(r).digest for r in resources}, 'schema': schema}
    if include_runtime_identity:
        identity['runtimes'] = {r: frozen.artifact(r).runtime_lock for r in resources if frozen.get(r).kind == 'block'}
    if children:
        identity['services'] = {service + '/' + instance: child.content_digest
                                for (service, instance), child in sorted(children.items())}
    digest = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return FlowSnapshot('ins_' + uuid4().hex, draft.model_dump_json(by_alias=True), frozen,
        MappingProxyType(packages), json.dumps(configuration), json.dumps(schema), digest, graph)
