"""API 地址来自环境，方法和相对路径来自固定能力绑定。"""
from .http import JsonTransport


class APIAdapter:
    def __init__(self, credentials):
        self.transport = JsonTransport(credentials)

    async def call(self, connection, binding, value):
        url = connection.base_url.rstrip('/') + binding.api_path
        return await self.transport.request(connection, binding.api_method, url, value.model_dump(mode='json', by_alias=True))

    async def close(self):
        await self.transport.close()
