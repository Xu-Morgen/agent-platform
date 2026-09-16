"""预绑定监听端口，在 Uvicorn 完成启动后通过专用管道握手。"""
import asyncio
import os
import socket
import uvicorn
from .application import create_app
from .contracts.control import Ready, StartupError
from .contracts.errors import ErrorResponse


async def serve(host: str, port: int, control_fd: int | None = None) -> None:
    channel = os.fdopen(os.dup(control_fd), 'w', encoding='utf-8', buffering=1) if control_fd is not None else None
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def send(message):
        if channel:
            channel.write(message.model_dump_json(by_alias=True) + '\n')
            channel.flush()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            if self.started:
                address_host, address_port = listener.getsockname()
                # 0.0.0.0 是监听地址；父进程通过 loopback 健康检查。
                address_host = '127.0.0.1' if address_host == '0.0.0.0' else address_host
                send(Ready(address=f'http://{address_host}:{address_port}'))

    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(128)
        listener.setblocking(False)
        server = Server(uvicorn.Config(create_app(), host=host, port=port, workers=1))
        await server.serve(sockets=[listener])
    except Exception:
        send(StartupError(error=ErrorResponse(
            code='STARTUP_ERROR', stage='startup.listen', message='后端监听或启动失败，请检查监听地址与端口',
        )))
        raise
    finally:
        listener.close()
        if channel:
            channel.close()
