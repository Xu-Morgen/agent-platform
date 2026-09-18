"""平台内部文档仓储；与业务块访问外部数据库无关。"""
from copy import deepcopy
from typing import Protocol
import os

from ..contracts.errors import ErrorResponse, PlatformError


def storage_error(message='存储不可用，操作未确认成功，请检查数据库后重启后端'):
    return PlatformError(ErrorResponse(code='STORAGE_ERROR', stage='storage', message=message), 503)


class DocumentStore(Protocol):
    durable: bool
    def read(self, collection: str) -> dict[str, dict]: ...
    def write(self, documents: list[tuple[str, str, dict]]) -> None: ...
    def check(self) -> None: ...
    def close(self) -> None: ...


class MemoryStore:
    durable = False

    def __init__(self):
        self._documents = {}

    def read(self, collection):
        return deepcopy(self._documents.get(collection, {}))

    def write(self, documents):
        prepared = [(collection, key, deepcopy(value)) for collection, key, value in documents]
        updated = self._documents.copy()
        for collection in {collection for collection, _, _ in prepared}:
            updated[collection] = updated.get(collection, {}).copy()
        for collection, key, value in prepared:
            updated[collection][key] = value
        self._documents = updated

    def check(self):
        pass

    def close(self):
        pass


def configured_store():
    url = os.environ.get('AGENT_PLATFORM_DATABASE_URL')
    if url:
        from .postgres import PostgresStore
        return PostgresStore(url)
    raise storage_error("数据库尚未初始化；请通过桌面或 python -m agent_platform 启动本地持久化后端")
