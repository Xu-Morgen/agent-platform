"""后端应用工厂；业务接口随任务卡逐步接入。"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    return FastAPI(title="Agent Platform")
