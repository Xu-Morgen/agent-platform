"""服务保存的同步临界区；所有验证成功后才写入版本与当前指针。"""
from uuid import uuid4
from .contracts.services import ServiceView, VersionView, ServiceSchema
from .registry.validation import invalid
from .versions.snapshots import SnapshotRepository, prepare_snapshot
from .versions.numbering import VersionAllocator


class ServiceManager:
    def __init__(self, definitions, packages, blocks, environments):
        self.definitions, self.packages, self.blocks, self.environments = definitions, packages, blocks, environments
        self.snapshots = SnapshotRepository()
        self.allocator = VersionAllocator()
        self._services = {}
        self._history = {}
        self._sources = {}

    def get(self, service_id):
        if service_id not in self._services:
            raise invalid('服务不存在', ['serviceId'], code='RECORD_NOT_FOUND')
        return self._services[service_id].model_copy(deep=True)

    def list(self):
        return [value.model_copy(deep=True) for value in self._services.values()]

    def resolve_current(self, service_id):
        return self.snapshots.get(self.get(service_id).active_instance_id)

    def save(self, request, service_id=None):
        previous = self.get(service_id) if service_id else None
        loaded = self.definitions.get(request.definition_load_id)
        if request.definition.definition_id != loaded.definition.definition_id:
            raise invalid('定义标识与加载内容不一致', ['definition', 'definitionId'])
        candidate = prepare_snapshot(request.definition, loaded.content, self.packages, self.blocks, self.environments)
        key = service_id or 'svc_' + uuid4().hex
        current = self.resolve_current(key) if previous else None
        # 单事件循环内无 await；验证结束后一次性分配、入库、切换。
        number = self.allocator.allocate(key, current, candidate)
        view = VersionView(instance_id=candidate.instance_id, revision=number.revision,
                           version=number.version, change_kind=number.change_kind, content_digest=candidate.content_digest)
        service = ServiceView(service_id=key, name=request.name, active_instance_id=candidate.instance_id, current=view)
        self.snapshots.add(candidate)
        self._sources[candidate.instance_id] = request.definition_load_id
        self._history.setdefault(key, []).append(view)
        self._services[key] = service
        return service.model_copy(deep=True)

    def schema(self, service_id):
        service = self.get(service_id)
        snapshot = self.resolve_current(service_id)
        return ServiceSchema(service=service, **snapshot.schema, definition=snapshot.definition,
                             definition_load_id=self._sources[snapshot.instance_id], configuration=snapshot.configuration)
