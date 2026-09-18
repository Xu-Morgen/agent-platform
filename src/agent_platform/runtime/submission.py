"""原子受理：固定实际实例与环境后入队，不在 HTTP 中执行。"""
from asyncio import Queue
from dataclasses import dataclass
from ..contracts.flows import NodeConfiguration
from ..flows.execution import checked, plain
from ..flows.configuration import validate_configurations
from ..flows.validation import validate_flow
from ..contracts.errors import ErrorResponse, PlatformError


@dataclass(frozen=True)
class PendingRun:
    run_id: str
    snapshot: object


class RunSubmission:
    def __init__(self, services, environments, runs):
        self.services, self.environments, self.runs = services, environments, runs
        self.queue = Queue()
        self.stopping = False

    def submit(self, request):
        self.runs.store.check()
        if self.stopping:
            raise PlatformError(ErrorResponse(code='APPLICATION_EXIT', stage='runs.submit', message='应用正在退出'), 503)
        with self.environments.lock:
            service = self.services.get(request.service_id)
            if request.expected_instance_id and request.expected_instance_id != service.active_instance_id:
                raise PlatformError(ErrorResponse(code='VERSION_CONFLICT', stage='runs.submit', message='当前实例已变化'), 409)
            snapshot = self.services.resolve_current(request.service_id)
            draft = snapshot.draft
            ports = validate_flow(draft, snapshot.catalog)
            if not ports.valid:
                raise PlatformError(ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='runs.submit',
                    message='输入输出契约校验失败，请添加通用块完成转换并重新保存', issues=ports.issues))
            value = checked(snapshot.catalog.contract(draft.input_contract), request.input, 'runs.input')
            validation = validate_configurations(draft, snapshot.catalog, self.environments)
            if not validation.valid:
                raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='runs.submit',
                    message='当前环境或节点配置校验失败', issues=validation.issues))
            ids = {(config.model if isinstance(config, NodeConfiguration) else config.api).environment_id
                   for config in draft.node_configurations.values()}
            environments = {key: self.environments.get(key) for key in sorted(ids)}
            run = self.runs.create(service_id=service.service_id, instance_id=snapshot.instance_id,
                version=service.current.version, revision=service.current.revision,
                input=plain(value), environment_snapshot=list(environments.values()))
            self.environments.occupy(environments, run.run_id)
            self.queue.put_nowait(PendingRun(run.run_id, snapshot))
            return run
