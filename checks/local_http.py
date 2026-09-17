"""仅供定向验收的可控本地 TCP/HTTP 服务，不是模型。"""
import asyncio
import json
from contextlib import asynccontextmanager


@asynccontextmanager
async def local_http(responder):
    tasks = set()
    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            head = await reader.readuntil(b'\r\n\r\n')
            length = next((int(line.split(b':',1)[1]) for line in head.split(b'\r\n') if line.lower().startswith(b'content-length:')), 0)
            body = await reader.readexactly(length)
            status, data = await responder(head, body, reader)
            data = data if isinstance(data, bytes) else json.dumps(data).encode()
            writer.write(f'HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n'.encode() + data)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)
    server = await asyncio.start_server(handle, '127.0.0.1', 0)
    try:
        yield f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}'
    finally:
        server.close()
        await server.wait_closed()
        for task in list(tasks): task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
