"""服务保存的同步临界区；所有验证成功后才写入版本与当前指针。"""
from uuid import uuid4
from .contracts.services import ServiceView, VersionView, ServiceSchema
from .contracts.base import StrictModel
from .registry.validation import invalid
from .versions.snapshots import SnapshotRepository
from .versions.numbering import VersionAllocator


class ServiceManager:
    def __init__(self, catalog, environments, store=None):
        self.catalog = catalog
        self.environments = environments
        self.snapshots = SnapshotRepository()
        self.allocator = VersionAllocator()
        self._services = {}
        self._history = {}
        from .storage import MemoryStore
        self.store = store or MemoryStore()
        self._restore()

    def _restore(self):
        from dataclasses import replace
        from .contracts.flows import FlowDraft
        from .flows.snapshots import compile_snapshot
        from .flows.execution import COMPILER_VERSION
        from .versions.numbering import VersionNumber
        for instance_id, document in self.store.read('instances').items():
            if document['compilerVersion'] != COMPILER_VERSION:
                raise ValueError('实例编译器版本不兼容')
            snapshot = compile_snapshot(FlowDraft.model_validate(document['flow']), self.catalog, restoring=True)
            if snapshot.content_digest != document['contentDigest']:
                raise ValueError('实例内容摘要不一致')
            self.snapshots.add(replace(snapshot, instance_id=instance_id))
        for key, document in self.store.read('services').items():
            service = ServiceView.model_validate(document['service'])
            history = [VersionView.model_validate(value) for value in document['history']]
            if not history or service.current not in history or service.active_instance_id != service.current.instance_id:
                raise ValueError('服务历史与当前指针不一致')
            for version in history:
                if self.snapshots.get(version.instance_id).content_digest != version.content_digest:
                    raise ValueError('服务版本与实例摘要不一致')
            self._services[key], self._history[key] = service, history
            latest = max(history, key=lambda value: value.revision)
            major, minor = map(int, latest.version.split('.'))
            self.allocator._last[key] = VersionNumber(latest.revision, major, minor, latest.change_kind)

    @staticmethod
    def _document(service, history):
        return {'service': service.model_dump(mode='json'),
                'history': [value.model_dump(mode='json') for value in history]}

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
        from .flows.snapshots import prepare_flow_snapshot
        candidate = prepare_flow_snapshot(request.flow, self.catalog, self.environments)
        key = service_id or 'svc_' + uuid4().hex
        current = self.resolve_current(key) if previous else None
        # 单事件循环内无 await；验证结束后一次性分配、入库、切换。
        from copy import deepcopy
        allocator = deepcopy(self.allocator)
        number = allocator.allocate(key, current, candidate)
        view = VersionView(instance_id=candidate.instance_id, revision=number.revision,
                           version=number.version, change_kind=number.change_kind, content_digest=candidate.content_digest)
        service = ServiceView(service_id=key, name=request.name, active_instance_id=candidate.instance_id, current=view)
        history = [*self._history.get(key, []), view]
        self.store.write([
            ('instances', candidate.instance_id, {'flow': candidate.draft.model_dump(mode='json'),
                'compilerVersion': candidate.compiler_version, 'contentDigest': candidate.content_digest}),
            ('services', key, self._document(service, history)),
        ])
        self.allocator = allocator
        self.snapshots.add(candidate)
        self._history[key] = history
        self._services[key] = service
        return service.model_copy(deep=True)

    def schema(self, service_id):
        service = self.get(service_id)
        snapshot = self.resolve_current(service_id)
        configuration_schemas = {
            'packages.' + binding: (artifact.content.load(artifact.manifest.contract_refs.configuration)
                                    if artifact.manifest.contract_refs.configuration else StrictModel).model_json_schema()
            for binding, artifact in snapshot.packages.items()
        }
        return ServiceSchema(service=service, **snapshot.schema, flow=snapshot.draft,
            compiler_version=snapshot.compiler_version, configuration=snapshot.configuration,
            configuration_schemas=configuration_schemas)

    def history(self, service_id):
        self.get(service_id)
        return [value.model_copy(deep=True) for value in self._history[service_id]]

    def historical(self, service_id, instance_id):
        from .contracts.services import FlowHistory
        version = next((v for v in self.history(service_id) if v.instance_id == instance_id), None)
        if version is None:
            raise invalid('该实例不属于此服务的历史', ['instanceId'], code='RECORD_NOT_FOUND')
        snapshot = self.snapshots.get(instance_id)
        return FlowHistory(version=version, flow=snapshot.draft, compiler_version=snapshot.compiler_version,
            configuration=snapshot.configuration, **snapshot.schema)

    def activate(self, service_id, instance_id):
        from .flows.drafts import preflight
        service = self.get(service_id)
        version = next((value for value in self._history[service_id] if value.instance_id == instance_id), None)
        if version is None:
            raise invalid('该实例不属于此服务的历史', ['instanceId'], code='RECORD_NOT_FOUND')
        snapshot = self.snapshots.get(instance_id)
        # 只校验当前环境；入口、包和块继续使用历史快照，不重读源目录。
        result = preflight(snapshot.draft.model_dump(by_alias=True), snapshot.catalog, self.environments)
        if not result.valid:
            from .contracts.errors import PlatformError, ErrorResponse
            raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='flow.activate', message='历史实例当前环境校验失败', issues=result.issues))
        service.active_instance_id = instance_id
        service.current = version.model_copy(deep=True)
        self.store.write([('services', service_id, self._document(service, self._history[service_id]))])
        self._services[service_id] = service
        return service.model_copy(deep=True)
