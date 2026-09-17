"""复用实际模型传输测试草稿连接，不保存环境、不创建业务任务。"""
import asyncio
from contextlib import asynccontextmanager
from time import monotonic
from .adapters.models import ModelAdapters
from .contracts.connection_tools import ModelListResult, ConnectionTestResult
from .contracts.models import ModelRequest
from .contracts.errors import ErrorResponse, PlatformError, upstream_error
from .repositories.credentials import CredentialRepository


class ConnectionTools:
    def __init__(self, credentials):
        self.credentials = credentials
        self._active = set()
        self._closed = False

    @asynccontextmanager
    async def session(self, connection):
        if self._closed:
            raise upstream_error('model')
        # 新凭据仅存在于本次请求；已有凭据复用引用，不增加会话仓储记录。
        credentials = CredentialRepository()
        connection = connection.model_copy(deep=True)
        secret = connection.credential
        if secret is None and connection.credential_ref:
            secret = self.credentials.resolve_for_transport(connection.credential_ref)
        if secret is not None:
            connection.credential_ref = None
            connection.credential = None
            connection.credential_ref = credentials.put(secret).credential_ref
        adapters = ModelAdapters(credentials)
        self._active.add(adapters)
        try:
            yield connection, adapters.for_connection(connection)
        finally:
            await adapters.close()
            credentials.clear()
            self._active.discard(adapters)

    async def models(self, value):
        start = monotonic()
        async with self.session(value.connection) as (connection, adapter):
            openai = connection.model_adapter == 'openai-chat'
            response = await adapter.transport.request(connection, 'GET',
                connection.base_url.rstrip('/') + ('/models' if openai else '/api/tags'), {}, kind='model')
            entries = response.get('data' if openai else 'models') if isinstance(response, dict) else None
            key = 'id' if openai else 'name'
            if not isinstance(entries, list) or any(not isinstance(item, dict)
                    or not isinstance(item.get(key), str) or not item[key].strip() for item in entries):
                raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='model.discovery',
                    message='模型列表响应格式无效'), 502)
            return ModelListResult(models=sorted({item[key] for item in entries}),
                elapsed_ms=round((monotonic() - start) * 1000))

    async def test(self, value):
        start = monotonic()
        async with self.session(value.connection) as (connection, adapter):
            response = await adapter.invoke(connection, ModelRequest(
                messages=[{'role': 'user', 'content': 'Connection test. Return only this JSON object: {"ok": true}'}],
                max_output_tokens=value.max_output_tokens))
            if response.output != {'ok': True} or type(response.output.get('ok')) is not bool:
                raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='model.test',
                    message='模型已响应，但未返回测试要求的 JSON 对象'), 502)
            return ConnectionTestResult(elapsed_ms=round((monotonic() - start) * 1000), usage=response.usage)

    async def close(self):
        self._closed = True
        await asyncio.gather(*(adapters.close() for adapters in list(self._active)))
