"""对应环境中的子进程适配器，主进程只保留源码、公开 Schema 和锁。"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from pydantic import TypeAdapter
from ..contracts.errors import ErrorResponse, PlatformError
from ..preparation.manager import Preparation, failed


class RemoteAdapter(TypeAdapter):
    def __init__(self, artifact, direction, schema):
        self.artifact, self.direction, self.schema = artifact, direction, schema
        self.core_schema = {'type': 'function-plain'} if schema.get('x-runtime-contract') else {'type': 'any'}
        self.validation_shape = artifact.validation_shapes.get(direction)

    def json_schema(self, **kwargs):
        return deepcopy(self.schema)

    def validate_python(self, value, **kwargs):
        # 真正的自定义 Pydantic 校验在对应环境中执行。
        return self.artifact.exchange('validate', value=value, direction=self.direction)


class ProcessBlock:
    def __init__(self, content, metadata, manager, environment, operation=None):
        self.content, self.manager, self.environment = content, manager, environment
        self.metadata_json = metadata.model_dump_json()
        self._preparation = operation
        try:
            schemas = self.exchange('describe')
        finally:
            self._preparation = None
        self.validation_shapes = schemas.get('validationShapes', {})
        self.input_adapter = RemoteAdapter(self, 'input', schemas['input'])
        self.output_adapter = RemoteAdapter(self, 'output', schemas['output'])
        self.primary_adapter = RemoteAdapter(self, 'primary', schemas['primary']) if 'primary' in schemas else None

    @property
    def metadata(self):
        from .single import BlockMetadata
        return BlockMetadata.model_validate_json(self.metadata_json)

    @property
    def runtime_lock(self):
        return deepcopy(self.environment['lock'])

    def request(self, action, **values):
        return {'protocolVersion': 1, 'action': action, 'source': base64.b64encode(self.content.files['block.py']).decode(),
                'digest': self.content.digest, **values}

    def command(self):
        return [self.environment['python'], '-m', 'agent_platform.blocks.worker']

    def environ(self):
        # API/数据库/主密钥留在父进程，块只接收运行所需的基本环境。
        allowed = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR', 'SYSTEMROOT'}
        env = {key: value for key, value in os.environ.items() if key in allowed}
        env['PYTHONPATH'] = self.environment['sdkPath']
        env['PYTHONNOUSERSITE'] = '1'
        return env

    def decode(self, line):
        try:
            message = json.loads(line)
            if message['protocolVersion'] != 1:
                raise ValueError()
            return message
        except (ValueError, KeyError):
            raise failed('BLOCK_PROCESS_ERROR', '块执行协议无效') from None

    def result(self, message):
        if message['type'] == 'error':
            raise PlatformError(ErrorResponse.model_validate(message['error']))
        if message['type'] != 'result':
            raise failed('BLOCK_PROCESS_ERROR', '块执行响应无效')
        return message['value']

    def exchange(self, action, **values):
        operation = self._preparation or Preparation(timeout=30)
        if not Path(self.environment['python']).is_file() or not Path(self.environment['sdkPath']).is_dir():
            self.environment = self.manager.prepare(self.metadata, locked=self.runtime_lock, operation=operation)
        try:
            with tempfile.TemporaryFile() as input_file, tempfile.TemporaryFile() as output:
                input_file.write((json.dumps(self.request(action, **values)) + '\n').encode())
                input_file.seek(0)
                process = subprocess.Popen(self.command(), stdin=input_file, stdout=output,
                                           stderr=subprocess.DEVNULL, env=self.environ())
                try:
                    while process.poll() is None:
                        operation.check()
                        operation.cancel.wait(.05)
                    output.seek(0)
                    result = output.read()
                    if process.returncode or not result:
                        raise failed('BLOCK_PROCESS_ERROR', '块子进程意外退出')
                    return self.result(self.decode(result))
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try: process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
        except PlatformError as exc:
            if exc.error.code == 'PREPARATION_TIMEOUT' and self._preparation is None:
                raise failed('BLOCK_TIMEOUT', '块契约导出或校验超时') from None
            raise
        except OSError:
            raise failed('BLOCK_PROCESS_ERROR', '块执行环境不可用') from None

    async def invoke(self, value, *, api=None, context=None):
        import threading
        cancel = threading.Event()
        loop = asyncio.get_running_loop()
        operation = Preparation(cancel=cancel, progress=(lambda event: loop.call_soon_threadsafe(context._progress, event)) if context else None)
        preparing = asyncio.create_task(asyncio.to_thread(self.manager.prepare, self.metadata, locked=self.runtime_lock, operation=operation))
        from ..runtime.boundary import checkpoint
        process = None
        try:
            while not preparing.done():
                await checkpoint('block_prepare', 'block')
                await asyncio.sleep(.05)
            self.environment = await preparing
            files = {}
            if context and context._files and context._run_id:
                for file_id, document in list(context._files.items.items()):
                    if context._run_id in document['runIds']:
                        path = await asyncio.to_thread(context._files.resolve, document['reference'], run_id=context._run_id)
                        files[file_id] = {'reference': document['reference'], 'path': str(path)}
            process = await asyncio.create_subprocess_exec(*self.command(), env=self.environ(),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=16 * 1024 * 1024)
            async def send(message):
                process.stdin.write((json.dumps(message) + '\n').encode())
                await process.stdin.drain()
            await send(self.request('invoke', value=value, files=files, models=self.environment['models']))
            api_active = False
            async def communicate():
                nonlocal api_active
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        raise failed('BLOCK_PROCESS_ERROR', '块子进程意外退出')
                    message = self.decode(line)
                    if message['type'] == 'api':
                        api_active = True
                        try:
                            if api is None:
                                raise failed('DEPENDENCY_ERROR', 'API 连接未配置')
                            from pydantic import JsonValue
                            result = await api.request(message['method'], message.get('payload'), response_type=JsonValue)
                            await send({'protocolVersion': 1, 'type': 'result', 'value': result})
                        except PlatformError as exc:
                            await send({'protocolVersion': 1, 'type': 'error', 'error': exc.error.model_dump(mode='json', by_alias=True)})
                        finally:
                            api_active = False
                    elif message['type'] == 'progress':
                        if context:
                            context.progress(message['message'], current=message.get('current'), total=message.get('total'))
                    else:
                        result = self.result(message)
                        process.stdin.close()
                        await process.wait()
                        if process.returncode:
                            raise failed('BLOCK_PROCESS_ERROR', '块子进程异常退出')
                        return result
            communication = asyncio.create_task(communicate())
            try:
                async with asyncio.timeout(300):
                    while not communication.done():
                        await asyncio.sleep(.05)
                        # API 请求沿用原有“等待传输结束后取消”语义；纯计算可立即终止。
                        if not api_active:
                            await checkpoint('block_update', 'block')
                    return await communication
            except TimeoutError:
                raise failed('BLOCK_TIMEOUT', '块执行超过 300 秒限制') from None
            finally:
                communication.cancel()
                await asyncio.gather(communication, return_exceptions=True)
        finally:
            cancel.set()
            if not preparing.done():
                await asyncio.gather(preparing, return_exceptions=True)
            if process and process.returncode is None:
                process.terminate()
                try: await asyncio.wait_for(process.wait(), 2)
                except TimeoutError:
                    process.kill()
                    await process.wait()
