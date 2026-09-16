"""后端应用及就绪生命周期。"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .contracts.health import HealthResponse
from .contracts.errors import ErrorResponse, PlatformError
from .http_errors import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = True
    try:
        yield
    finally:
        app.state.ready = False


def create_app() -> FastAPI:
    app = FastAPI(title='Agent Platform', lifespan=lifespan)
    app.state.ready = False
    register_error_handlers(app)

    @app.get('/api/v1/health', response_model=HealthResponse)
    async def health() -> HealthResponse:
        if not app.state.ready:
            raise PlatformError(ErrorResponse(
                code='BACKEND_UNAVAILABLE', stage='lifecycle', message='后端尚未就绪',
            ), 503)
        return HealthResponse(status='ready')

    return app
