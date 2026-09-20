"""版本 1 JSON 行协议；stdout 专用于通信，业务 print 重定向到 stderr。"""
import asyncio
import base64
import contextlib
import json
import sys
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4
from pydantic import ValidationError
from ..contracts.errors import ErrorResponse, PlatformError
from ..registry.snapshots import ContentSnapshot, _MemoryFinder
from ..registry.single_blocks import SingleBlockRegistry
from .single import strict_adapter

PROTOCOL_VERSION = 1
channel = sys.stdout


def send(kind, **values):
    channel.write(json.dumps({'protocolVersion': PROTOCOL_VERSION, 'type': kind, **values}, ensure_ascii=False) + '\n')
    channel.flush()


def receive():
    line = sys.stdin.readline()
    if not line:
        raise RuntimeError('父进程已关闭')
    message = json.loads(line)
    if message.get('protocolVersion') != PROTOCOL_VERSION:
        raise RuntimeError('执行协议版本不一致')
    return message


class RemoteAPI:
    async def request(self, method, payload=None, *, response_type):
        send('api', method=method, payload=payload)
        message = receive()
        if message['type'] == 'error':
            raise PlatformError(ErrorResponse.model_validate(message['error']))
        try:
            return strict_adapter(response_type).validate_python(message['value'], strict=True)
        except ValidationError as exc:
            from ..validation_issues import validation_exception
            raise validation_exception(exc, stage='api.output', code='OUTPUT_VALIDATION_ERROR') from None


class RemoteContext:
    def __init__(self, files, models):
        self.files, self.models = files, models

    def file(self, reference):
        from ..contracts.files import FileReference
        from ..storage.files import file_error
        reference = FileReference.model_validate(reference)
        record = self.files.get(reference.file_id)
        if record is None or FileReference.model_validate(record['reference']) != reference:
            raise file_error('FILE_NOT_FOUND', '文件不属于当前任务')
        return Path(record['path'])

    def model(self, name):
        if name not in self.models:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='block.context', message='模型未就绪'))
        return Path(self.models[name])

    def progress(self, message, *, current=None, total=None):
        send('progress', message=str(message), current=current, total=total)


def plain(value):
    from pydantic import BaseModel
    return value.model_dump(mode='json', by_alias=True) if isinstance(value, BaseModel) else value


async def main():
    request = receive()
    source = base64.b64decode(request['source'], validate=True)
    snapshot = ContentSnapshot(request['digest'], '_agent_worker_' + uuid4().hex, MappingProxyType({'block.py': source}))
    sys.meta_path.insert(0, _MemoryFinder(snapshot))
    try:
        with contextlib.redirect_stdout(sys.stderr):
            artifact = SingleBlockRegistry(local=True).load_content(snapshot)
            action = request['action']
            if action == 'describe':
                from ..registry.catalog import ContractResource
                result = {direction: ContractResource(adapter, request['digest'] + ':' + direction).schema
                          for direction, adapter in [('input', artifact.input_adapter), ('output', artifact.output_adapter)]}
            elif action == 'validate':
                adapter = artifact.input_adapter if request['direction'] == 'input' else artifact.output_adapter
                result = plain(adapter.validate_python(request['value'], strict=True))
            elif action == 'invoke':
                result = plain(await artifact.invoke(request['value'], api=RemoteAPI() if artifact.metadata.uses_api else None,
                    context=RemoteContext(request.get('files', {}), request.get('models', {}))))
            else:
                raise ValueError('未知执行消息')
        send('result', value=result)
    except PlatformError as exc:
        send('error', error=exc.error.model_dump(mode='json', by_alias=True))
    except ValidationError as exc:
        from ..validation_issues import validation_exception
        error = validation_exception(exc, stage='block.' + request.get('direction', 'input'))
        send('error', error=error.error.model_dump(mode='json', by_alias=True))
    except BaseException:
        send('error', error=ErrorResponse(code='BLOCK_PROCESS_ERROR', stage='block.process', message='块子进程导入或执行失败；请检查依赖系统库及块实现').model_dump(mode='json', by_alias=True))
    finally:
        snapshot.close()


if __name__ == '__main__':
    asyncio.run(main())
