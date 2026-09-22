"""后端应用及就绪生命周期。"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from .contracts.environments import Environment, EnvironmentWrite
from .contracts.connection_tools import ModelListRequest, ModelListResult, ConnectionTestRequest, ConnectionTestResult
from .contracts.services import ServiceWrite, ServiceView, ServiceSchema, VersionView, ActivateRequest, FlowHistory, ServiceComponent
from .contracts.runs import Run, RunSubmit, RunResult, RunStatus
from .contracts.health import HealthResponse
from .contracts.errors import ErrorResponse, PlatformError
from .http_errors import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.worker.start()
    app.state.ready = True
    try:
        yield
    finally:
        app.state.ready = False
        try:
            await app.state.connection_tools.close()
            await app.state.preparations.close()
            await app.state.worker.stop()
            await app.state.ocr_jobs.close()
            await app.state.ocr_processes.close()
            await app.state.embedding_jobs.close()
            await app.state.embedding_processes.close()
        finally:
            app.state.credentials.clear()
            app.state.catalog.close()
            app.state.files.close()
            app.state.knowledge.close()
            app.state.embedding.close()
            app.state.ocr.close()
            app.state.store.close()


def create_app(store=None) -> FastAPI:
    from .storage import configured_store
    store = store or configured_store()
    try:
        return _create_app(store)
    except Exception:
        store.close()
        raise


def _create_app(store) -> FastAPI:
    app = FastAPI(title='Agent Platform', lifespan=lifespan)
    app.state.ready = False
    app.state.store = store
    from .repositories.settings import SettingsRepository
    from .contracts.settings import PlatformSettingsWrite, PlatformSettingsView
    app.state.settings = SettingsRepository(store)
    register_error_handlers(app)
    from .repositories.credentials import CredentialRepository
    from .repositories.environments import EnvironmentRepository
    app.state.credentials = CredentialRepository(store)
    app.state.environments = EnvironmentRepository(app.state.credentials, store)
    from .connection_tools import ConnectionTools
    app.state.connection_tools = ConnectionTools(app.state.credentials)

    from .registry.packages import PackageRegistry
    from .flows.configuration import NodeValidationRequest, NodeValidationResult, validate_node
    from .contracts.flows import FlowDraft
    from .flows.validation import ValidationResult, validate_flow
    from .registry.catalog import ModuleCatalog
    from .contracts.catalog import CatalogArchive, CatalogLoad, CatalogResource, ContractGroup
    from .services import ServiceManager
    app.state.packages = PackageRegistry()
    app.state.catalog = ModuleCatalog(app.state.packages, store)
    from .preparation.jobs import PreparationJobs
    app.state.preparations = PreparationJobs(app.state.catalog)
    from .flows.drafts import DraftRepository, preflight
    from .contracts.drafts import DraftWrite, DraftDocument
    app.state.drafts = DraftRepository(store)
    app.state.services = ServiceManager(app.state.catalog, app.state.environments, store)

    from .repositories.runs import RunRepository
    from .runtime.submission import RunSubmission
    app.state.runs = RunRepository(store)
    from .storage.files import TaskFiles
    from .contracts.files import FileReference
    import os
    app.state.files = TaskFiles(store, max_bytes=int(os.environ.get('AGENT_PLATFORM_FILE_MAX_BYTES', 50 * 1024 * 1024)))
    from .repositories.knowledge import KnowledgeRepository
    app.state.knowledge = KnowledgeRepository(store)
    from .knowledge_routes import register_knowledge_routes
    register_knowledge_routes(app)
    from .embedding.process import EmbeddingProcesses
    from .embedding.repository import EmbeddingRepository
    from .embedding.routes import register_routes
    app.state.embedding_processes = EmbeddingProcesses()
    app.state.embedding = EmbeddingRepository(store, app.state.embedding_processes)
    register_routes(app)
    from .ocr.process import OCRProcesses
    from .ocr.repository import OCRRepository
    from .ocr.routes import register_routes as register_ocr_routes
    app.state.ocr_processes = OCRProcesses()
    app.state.ocr = OCRRepository(store, app.state.ocr_processes)
    register_ocr_routes(app)
    app.state.submission = RunSubmission(app.state.services, app.state.environments, app.state.runs, app.state.files, app.state.knowledge, app.state.embedding, app.state.ocr)

    from .runtime.worker import RunWorker
    app.state.worker = RunWorker(app.state.submission, concurrency=app.state.settings.active_run_concurrency)

    @app.get('/api/v1/settings', response_model=PlatformSettingsView)
    async def platform_settings():
        return app.state.settings.get()

    @app.put('/api/v1/settings', response_model=PlatformSettingsView)
    async def save_platform_settings(value: PlatformSettingsWrite):
        return app.state.settings.save(value)

    @app.post('/api/v1/files', response_model=FileReference, status_code=201)
    async def upload_file(request: Request, name: str = Query(min_length=1, max_length=255)):
        return await app.state.files.save(name, request.stream())

    @app.delete('/api/v1/files/{file_id}', status_code=204)
    async def remove_file(file_id: str):
        app.state.files.remove(file_id)

    @app.get('/api/v1/platform')
    async def platform_info():
        import os
        return {'product': '可控 Agent 工作流平台',
                'storage': 'postgresql' if store.durable else 'memory',
                'persistent': store.durable, 'automaticResume': False,
                'dataDirectory': os.environ.get('AGENT_PLATFORM_DATA_DIR') if store.durable else None}

    @app.get('/api/v1/runs', response_model=list[Run])
    async def list_runs(service_id: str | None = Query(None, alias='serviceId'),
                        status: RunStatus | None = None, limit: int = Query(50, ge=1, le=200),
                        offset: int = Query(0, ge=0)):
        return app.state.runs.list(service_id=service_id, status=status, limit=limit, offset=offset)

    @app.post('/api/v1/runs/{run_id}/cancel', response_model=Run)
    async def cancel(run_id: str):
        from .runtime.cancellation import cancel_run
        return cancel_run(app.state.submission, run_id)

    @app.get('/api/v1/runs/{run_id}', response_model=Run)
    async def run_status(run_id: str):
        return app.state.runs.get(run_id)

    @app.get('/api/v1/runs/{run_id}/result', response_model=RunResult)
    async def run_result(run_id: str):
        from .runtime.queries import result_for
        return result_for(app.state.runs, run_id)

    @app.post('/api/v1/runs', response_model=Run, status_code=202)
    async def submit_run(value: RunSubmit):
        import asyncio
        from .flows.execution import checked
        require_worker()
        snapshot = app.state.services.resolve_current(value.service_id)
        request = value.model_copy(deep=True)
        if request.expected_instance_id is None:
            request.expected_instance_id = snapshot.instance_id
        parsed = await asyncio.to_thread(checked, snapshot.catalog.contract(snapshot.draft.input_contract), value.input, 'runs.input')
        require_worker()
        return app.state.submission.submit(request, validated_input=parsed)

    @app.post('/api/v1/drafts', response_model=DraftDocument, status_code=201)
    async def create_draft(value: DraftWrite):
        return app.state.drafts.save(value)

    @app.get('/api/v1/drafts', response_model=list[DraftDocument])
    async def list_drafts():
        return app.state.drafts.list()

    @app.get('/api/v1/drafts/{draft_id}', response_model=DraftDocument)
    async def get_draft(draft_id: str):
        return app.state.drafts.get(draft_id)

    @app.put('/api/v1/drafts/{draft_id}', response_model=DraftDocument)
    async def update_draft(draft_id: str, value: DraftWrite):
        return app.state.drafts.save(value, draft_id)

    @app.post('/api/v1/drafts/{draft_id}/validate', response_model=ValidationResult)
    async def validate_saved_draft(draft_id: str):
        document = app.state.drafts.get(draft_id)
        return preflight(document.content, app.state.catalog, app.state.environments)

    @app.post('/api/v1/flows/validate', response_model=ValidationResult)
    async def validate_complete_flow(value: DraftWrite):
        return preflight(value.content, app.state.catalog, app.state.environments)

    @app.post('/api/v1/flows/validate-node', response_model=NodeValidationResult)
    async def validate_node_configuration(value: NodeValidationRequest):
        return validate_node(value, app.state.catalog, app.state.environments)

    @app.post('/api/v1/flows/validate-ports', response_model=ValidationResult)
    async def validate_ports(value: FlowDraft):
        return validate_flow(value, app.state.catalog)

    @app.post('/api/v1/catalog/load', response_model=CatalogResource)
    async def catalog_load(value: CatalogLoad):
        import asyncio
        job = app.state.preparations.start(value)
        try:
            await asyncio.shield(app.state.preparations.tasks[job['jobId']])
        except asyncio.CancelledError:
            app.state.preparations.cancel(job['jobId'])
            raise
        result = app.state.preparations.get(job['jobId'])
        if result['error']:
            raise PlatformError(ErrorResponse.model_validate(result['error']), 422)
        return result['resource']

    @app.post('/api/v1/preparations', status_code=202)
    async def prepare_resource(value: CatalogLoad):
        return app.state.preparations.start(value)

    @app.get('/api/v1/preparations/{job_id}')
    async def preparation_status(job_id: str):
        return app.state.preparations.get(job_id)

    @app.post('/api/v1/preparations/{job_id}/cancel')
    async def cancel_preparation(job_id: str):
        return app.state.preparations.cancel(job_id)

    @app.get('/api/v1/catalog', response_model=list[CatalogResource])
    async def catalog_list():
        return app.state.catalog.list()

    @app.get('/api/v1/contracts', response_model=list[ContractGroup])
    async def contract_groups():
        return app.state.catalog.contract_groups()

    @app.patch('/api/v1/catalog/{resource_id}', response_model=CatalogResource)
    async def catalog_archive(resource_id: str, value: CatalogArchive):
        return app.state.catalog.set_archived(resource_id, value.archived)

    @app.get('/api/v1/catalog/{resource_id}', response_model=CatalogResource)
    async def catalog_get(resource_id: str):
        return app.state.catalog.get(resource_id)

    @app.get('/api/v1/services', response_model=list[ServiceView])
    async def services():
        return app.state.services.list()

    @app.get('/api/v1/service-components', response_model=list[ServiceComponent])
    async def service_components():
        return app.state.services.components()

    @app.post('/api/v1/services', response_model=ServiceView, status_code=201)
    async def create_service(value: ServiceWrite):
        return app.state.services.save(value)

    @app.post('/api/v1/services/{service_id}/versions', response_model=ServiceView, status_code=201)
    async def save_version(service_id: str, value: ServiceWrite):
        return app.state.services.save(value, service_id)

    @app.get('/api/v1/services/{service_id}/versions', response_model=list[VersionView])
    async def version_history(service_id: str):
        return app.state.services.history(service_id)

    @app.get('/api/v1/services/{service_id}/versions/{instance_id}', response_model=FlowHistory)
    async def historical_version(service_id: str, instance_id: str):
        return app.state.services.historical(service_id, instance_id)

    @app.post('/api/v1/services/{service_id}/versions/{instance_id}/draft', response_model=DraftDocument, status_code=201)
    async def copy_historical_draft(service_id: str, instance_id: str):
        app.state.services.require_supported(instance_id)
        history = app.state.services.historical(service_id, instance_id)
        content = history.flow.model_dump(mode='json', by_alias=True)
        content.pop('draftId', None)
        return app.state.drafts.save(DraftWrite(content=content))

    @app.post('/api/v1/services/{service_id}/activate', response_model=ServiceView)
    async def activate_version(service_id: str, value: ActivateRequest):
        return app.state.services.activate(service_id, value.instance_id)

    @app.get('/api/v1/services/{service_id}/schema', response_model=ServiceSchema)
    async def service_schema(service_id: str):
        return app.state.services.schema(service_id)

    from .contracts.resource_advice import AdviceRequest, AdviceResult
    from .resource_advice import explain

    @app.post('/api/v1/resource-advice', response_model=AdviceResult)
    async def resource_advice(value: AdviceRequest):
        return await explain(value, app.state.catalog, app.state.environments, app.state.connection_tools)

    @app.get('/api/v1/environments', response_model=list[Environment])
    async def environments():
        return app.state.environments.list()

    @app.post('/api/v1/connection-tools/models', response_model=ModelListResult)
    async def connection_models(value: ModelListRequest):
        return await app.state.connection_tools.models(value)

    @app.post('/api/v1/connection-tools/test', response_model=ConnectionTestResult)
    async def connection_test(value: ConnectionTestRequest):
        return await app.state.connection_tools.test(value)

    @app.post('/api/v1/environments', response_model=Environment, status_code=201)
    async def create_environment(value: EnvironmentWrite):
        return app.state.environments.save(value)

    @app.put('/api/v1/environments/{environment_id}', response_model=Environment)
    async def update_environment(environment_id: str, value: EnvironmentWrite):
        return app.state.environments.save(value, environment_id)


    def require_worker():
        if not app.state.ready or not app.state.worker.healthy:
            raise PlatformError(ErrorResponse(code='BACKEND_UNAVAILABLE', stage='runtime',
                message='任务消费者池未就绪或已停止，请检查后端'), 503)

    @app.get('/api/v1/health', response_model=HealthResponse)
    async def health() -> HealthResponse:
        if not app.state.ready:
            raise PlatformError(ErrorResponse(
                code='BACKEND_UNAVAILABLE', stage='lifecycle', message='后端尚未就绪',
            ), 503)
        store.check()
        require_worker()
        return HealthResponse(status='ready')

    return app
