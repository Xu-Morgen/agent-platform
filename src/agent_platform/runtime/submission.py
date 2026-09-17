"""原子受理：固定实际实例与环境后入队，不在 HTTP 中执行。"""
from asyncio import Queue
from dataclasses import dataclass
from ..configuration import validate_environment_bindings
from ..contracts.errors import ErrorResponse, PlatformError
from .validation import validate


@dataclass(frozen=True)
class PendingRun:
    run_id: str
    snapshot: object


class RunSubmission:
    def __init__(self, services, environments, runs):
        self.services, self.environments, self.runs = services, environments, runs
        self.queue = Queue()

    def submit(self, request):
        with self.environments.lock:
            service = self.services.get(request.service_id)
            if request.expected_instance_id and request.expected_instance_id != service.active_instance_id:
                raise PlatformError(ErrorResponse(code='VERSION_CONFLICT', stage='runs.submit', message='当前实例已变化'), 409)
            snapshot = self.services.resolve_current(request.service_id)
            model = snapshot.content.load(snapshot.definition.input_model)
            value = validate(model, request.input, 'runs.input')
            environments = validate_environment_bindings(snapshot.definition, self.environments)
            run = self.runs.create(service_id=service.service_id, instance_id=snapshot.instance_id,
                version=service.current.version, revision=service.current.revision,
                input=value.model_dump(mode='json', by_alias=True), environment_snapshot=list(environments.values()))
            self.environments.occupy(environments, run.run_id)
            self.queue.put_nowait(PendingRun(run.run_id, snapshot))
            return run
