"""后端应用及就绪生命周期。"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .contracts.environments import Environment, EnvironmentWrite
from .contracts.registry import LoadRequest, LoadResult
from .registry.api import load_local
from .contracts.services import ServiceWrite, ServiceView, ServiceSchema, VersionView, ActivateRequest
from .contracts.runs import Run, RunSubmit, RunResult
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
        await app.state.worker.stop()


def create_app() -> FastAPI:
    app = FastAPI(title='Agent Platform', lifespan=lifespan)
    app.state.ready = False
    register_error_handlers(app)
    from .repositories.credentials import CredentialRepository
    from .repositories.environments import EnvironmentRepository
    app.state.credentials = CredentialRepository()
    app.state.environments = EnvironmentRepository(app.state.credentials)

    from .registry.packages import PackageRegistry
    from .registry.blocks import BlockRegistry
    from .registry.definitions import DefinitionRegistry
    from .services import ServiceManager
    app.state.packages = PackageRegistry()
    app.state.blocks = BlockRegistry()
    app.state.definitions = DefinitionRegistry()
    app.state.services = ServiceManager(app.state.definitions, app.state.packages, app.state.blocks, app.state.environments)

    from .repositories.runs import RunRepository
    from .runtime.submission import RunSubmission
    app.state.runs = RunRepository()
    app.state.submission = RunSubmission(app.state.services, app.state.environments, app.state.runs)

    from .runtime.worker import RunWorker
    app.state.worker = RunWorker(app.state.submission)

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
        return app.state.submission.submit(value)

    @app.post('/api/v1/registry/load', response_model=LoadResult)
    async def registry_load(value: LoadRequest):
        return load_local(app.state, value)

    @app.get('/api/v1/services', response_model=list[ServiceView])
    async def services():
        return app.state.services.list()

    @app.post('/api/v1/services', response_model=ServiceView, status_code=201)
    async def create_service(value: ServiceWrite):
        return app.state.services.save(value)

    @app.post('/api/v1/services/{service_id}/versions', response_model=ServiceView, status_code=201)
    async def save_version(service_id: str, value: ServiceWrite):
        return app.state.services.save(value, service_id)

    @app.get('/api/v1/services/{service_id}/versions', response_model=list[VersionView])
    async def version_history(service_id: str):
        return app.state.services.history(service_id)

    @app.post('/api/v1/services/{service_id}/activate', response_model=ServiceView)
    async def activate_version(service_id: str, value: ActivateRequest):
        return app.state.services.activate(service_id, value.instance_id)

    @app.get('/api/v1/services/{service_id}/schema', response_model=ServiceSchema)
    async def service_schema(service_id: str):
        return app.state.services.schema(service_id)

    @app.get('/api/v1/environments', response_model=list[Environment])
    async def environments():
        return app.state.environments.list()

    @app.post('/api/v1/environments', response_model=Environment, status_code=201)
    async def create_environment(value: EnvironmentWrite):
        return app.state.environments.save(value)

    @app.put('/api/v1/environments/{environment_id}', response_model=Environment)
    async def update_environment(environment_id: str, value: EnvironmentWrite):
        return app.state.environments.save(value, environment_id)


    @app.get('/api/v1/health', response_model=HealthResponse)
    async def health() -> HealthResponse:
        if not app.state.ready:
            raise PlatformError(ErrorResponse(
                code='BACKEND_UNAVAILABLE', stage='lifecycle', message='后端尚未就绪',
            ), 503)
        return HealthResponse(status='ready')

    return app
