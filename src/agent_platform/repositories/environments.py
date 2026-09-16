"""环境统一更新入口；任务占用检查由 I3 接入。"""
from uuid import uuid4
from ..contracts.environments import Connection, Environment, EnvironmentWrite
from ..contracts.errors import ErrorResponse, PlatformError
from .credentials import CredentialRepository


class EnvironmentRepository:
    def __init__(self, credentials: CredentialRepository):
        self.credentials = credentials
        self._items: dict[str, Environment] = {}

    def get(self, environment_id: str) -> Environment:
        if environment_id not in self._items:
            raise PlatformError(ErrorResponse(code='RECORD_NOT_FOUND', stage='environment',
                                             message='环境不存在', field_path=['environmentRefs']), 404)
        return self._items[environment_id].model_copy(deep=True)

    def list(self) -> list[Environment]:
        return [value.model_copy(deep=True) for value in self._items.values()]

    def save(self, request: EnvironmentWrite, environment_id: str | None = None) -> Environment:
        request = EnvironmentWrite.model_validate(request)
        previous = self.get(environment_id) if environment_id else None
        for connection in request.connections:
            if connection.credential_ref:
                self.credentials.get(connection.credential_ref)
        connections = []
        for connection in request.connections:
            data = connection.model_dump(exclude={'credential'})
            if connection.credential is not None:
                data['credential_ref'] = self.credentials.put(connection.credential).credential_ref
            connections.append(Connection.model_validate(data))
        value = Environment(environment_id=environment_id or 'env_' + uuid4().hex,
                            revision=previous.revision + 1 if previous else 1,
                            name=request.name, connections=connections)
        self._items[value.environment_id] = value
        return value.model_copy(deep=True)
