"""原子受理：固定实际实例与环境后入队，不在 HTTP 中执行。"""
from asyncio import Queue
from contextlib import nullcontext
from dataclasses import dataclass
from ..contracts.flows import NodeConfiguration
from ..flows.execution import checked, plain
from ..flows.configuration import validate_configurations
from ..contracts.errors import ErrorResponse, PlatformError

_UNVALIDATED = object()


@dataclass(frozen=True)
class PendingRun:
    run_id: str
    snapshot: object


class RunSubmission:
    def __init__(self, services, environments, runs, files=None, knowledge=None, embedding=None, ocr=None):
        self.services, self.environments, self.runs = services, environments, runs
        self.files = files
        self.knowledge = knowledge
        self.embedding = embedding
        self.ocr = ocr
        self.queue = Queue()
        self.stopping = False

    def submit(self, request, *, validated_input=_UNVALIDATED):
        self.runs.store.check()
        if self.stopping:
            raise PlatformError(ErrorResponse(code='APPLICATION_EXIT', stage='runs.submit', message='应用正在退出'), 503)
        with self.environments.lock, self.knowledge.lock if self.knowledge else nullcontext():
            service = self.services.get(request.service_id)
            if request.expected_instance_id and request.expected_instance_id != service.active_instance_id:
                raise PlatformError(ErrorResponse(code='VERSION_CONFLICT', stage='runs.submit', message='当前实例已变化'), 409)
            snapshot = self.services.resolve_current(request.service_id)
            embedding_snapshot = None
            if snapshot.requires_semantic_search:
                if self.embedding is None:
                    raise PlatformError(ErrorResponse(code='EMBEDDING_NOT_READY', stage='runs.submit',
                        message='语义检索模型管理器未就绪'))
                embedding_snapshot = self.embedding.fixed()
            ocr_snapshot = None
            if snapshot.requires_ocr:
                if self.ocr is None:
                    raise PlatformError(ErrorResponse(code='OCR_NOT_READY', stage='runs.submit',
                        message='OCR 模型管理器未就绪'))
                ocr_snapshot = self.ocr.fixed()
            draft = snapshot.draft
            value = (checked(snapshot.catalog.contract(draft.input_contract), request.input, 'runs.input')
                     if validated_input is _UNVALIDATED else validated_input)
            from .knowledge import bind_knowledge
            bound, knowledge_bindings = bind_knowledge(snapshot.catalog.contract(draft.input_contract).schema, plain(value), self.knowledge)
            if knowledge_bindings:
                value = checked(snapshot.catalog.contract(draft.input_contract), bound, 'runs.input')
            from ..storage.files import file_references
            references = file_references(snapshot.catalog.contract(draft.input_contract).schema, plain(value))
            if references and self.files is None:
                raise PlatformError(ErrorResponse(code='FILE_NOT_FOUND', stage='runs.input', message='任务文件存储不可用'))
            validation = validate_configurations(draft, snapshot.catalog, self.environments)
            if not validation.valid:
                raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='runs.submit',
                    message='当前环境或节点配置校验失败', issues=validation.issues))
            ids = {(config.model if isinstance(config, NodeConfiguration) else config.api).environment_id
                   for _, scope in snapshot.scopes() for config in scope.draft.node_configurations.values()}
            environments = {key: self.environments.get(key) for key in sorted(ids)}
            run = self.runs.create(service_id=service.service_id, instance_id=snapshot.instance_id,
                files=self.files, references=references,
                version=service.current.version, revision=service.current.revision,
                embedding_snapshot=embedding_snapshot, ocr_snapshot=ocr_snapshot, input=plain(value), knowledge_bindings=knowledge_bindings, environment_snapshot=list(environments.values()))
            self.environments.occupy(environments, run.run_id)
            self.queue.put_nowait(PendingRun(run.run_id, snapshot))
            return run
