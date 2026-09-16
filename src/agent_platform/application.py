"""后端应用工厂；业务接口随任务卡逐步接入。"""

from fastapi import FastAPI

from .http_errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Platform")
    register_error_handlers(app)
    return app
