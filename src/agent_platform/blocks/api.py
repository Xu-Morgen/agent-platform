"""API 块使用绑定连接访问相对路径，凭据与传输生命周期由平台管理。"""
from pydantic import ValidationError
from .single import strict_adapter
from ..contracts.errors import ErrorResponse, PlatformError
from ..runtime.boundary import checkpoint


class BlockAPI:
    def __init__(self, connection, transport, *, path):
        self._connection = connection
        self._transport = transport
        self._path = path

    async def request(self, method, payload=None, *, response_type):
        """使用节点快照中的路径；GET 的 payload 为查询参数，其余方法为 JSON。"""
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
            raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='api.request',
                message='API 请求须使用 GET/POST/PUT/PATCH/DELETE 方法'))
        adapter = strict_adapter(response_type)
        await checkpoint('api_start', 'api.request')
        result = await self._transport.request(self._connection, method,
            self._connection.base_url.rstrip('/') + '/' + self._path.lstrip('/'), payload, kind='api')
        await checkpoint('api_update', 'api.request')
        try:
            return adapter.validate_python(result, strict=True)
        except ValidationError as exc:
            from ..validation_issues import validation_exception
            raise validation_exception(exc, stage='api.output', code='OUTPUT_VALIDATION_ERROR') from None
