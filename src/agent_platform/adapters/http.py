"""一次请求、无重试；请求生命周期内持有可关闭的本地连接。"""
import asyncio
import httpx
from ..contracts.errors import ErrorResponse, PlatformError, upstream_error


class JsonTransport:
    def __init__(self, credentials):
        self.credentials = credentials
        self._clients = set()
        self._tasks = set()
        self.closed = False

    async def request(self, connection, method, url, payload, *, kind='api'):
        if self.closed:
            raise upstream_error(kind)
        headers = {}
        if connection.credential_ref:
            secret = self.credentials.resolve_for_transport(connection.credential_ref).get_secret_value()
            headers['Authorization'] = 'Bearer ' + secret
        client = httpx.AsyncClient(timeout=connection.timeout_seconds, follow_redirects=False, trust_env=False)
        task = asyncio.current_task()
        self._clients.add(client)
        self._tasks.add(task)
        try:
            async with asyncio.timeout(connection.timeout_seconds):
                response = await client.request(method, url, headers=headers,
                    **({'params': payload} if method == 'GET' else {'json': payload}))
            if not response.is_success:
                error = upstream_error(kind)
                error.error.details.http_status = response.status_code
                raise error
            try:
                return response.json()
            except ValueError:
                raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage=kind + '.output',
                                    message='上游响应不是有效 JSON'), 502) from None
        except (httpx.TimeoutException, TimeoutError):
            error = upstream_error(kind, timeout=True)
            error.error.details.timeout_seconds = connection.timeout_seconds
            raise error from None
        except httpx.HTTPError:
            raise upstream_error(kind) from None
        except asyncio.CancelledError:
            if self.closed:
                raise upstream_error(kind) from None
            raise
        finally:
            await client.aclose()
            self._clients.discard(client)
            self._tasks.discard(task)

    async def close(self):
        self.closed = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*(c.aclose() for c in list(self._clients)), return_exceptions=True)
        await asyncio.gather(*tasks, return_exceptions=True)
