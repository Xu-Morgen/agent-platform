"""预绑定监听端口，在 Uvicorn 完成启动后通过专用管道握手。"""
import asyncio
import os
import socket
import sys
import uvicorn
from .application import create_app
from .contracts.control import Ready, StartupError, Shutdown, parse_control
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
                send(Ready(protocol_version=1, type='ready', address=f'http://{address_host}:{address_port}'))

    loop = asyncio.get_running_loop()
    watching = False
    buffer = bytearray()
    stopping_task = None

    def stop():
        nonlocal watching, stopping_task
        server.config.app.state.ready = False
        server.should_exit = True
        if stopping_task is None:
            stopping_task = loop.create_task(server.config.app.state.worker.stop())
        if watching:
            loop.remove_reader(0)
            watching = False

    def control_input():
        try:
            chunk = os.read(0, 4096)
            if not chunk:
                stop()  # 父进程消失时不保留后台服务。
                return
            buffer.extend(chunk)
            if len(buffer) > 65536:
                raise ValueError('控制消息过长')
            while b'\n' in buffer:
                line, _, rest = buffer.partition(b'\n')
                buffer[:] = rest
                if not isinstance(parse_control(line.decode('utf-8')), Shutdown):
                    raise ValueError('父进程消息方向错误')
                stop()
        except (ValueError, OSError):
            print('控制管道无效，停止后端', file=sys.stderr)
            stop()

    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(128)
        listener.setblocking(False)
        server = Server(uvicorn.Config(create_app(), host=host, port=port, workers=1))
        if channel:
            loop.add_reader(0, control_input)
            watching = True
        await server.serve(sockets=[listener])
    except Exception:
        send(StartupError(protocol_version=1, type='startupError', error=ErrorResponse(
            code='STARTUP_ERROR', stage='startup.listen', message='后端监听或启动失败，请检查监听地址与端口',
        )))
        raise
    finally:
        if stopping_task is not None:
            await stopping_task
        if watching:
            loop.remove_reader(0)
        listener.close()
        if channel:
            channel.close()
