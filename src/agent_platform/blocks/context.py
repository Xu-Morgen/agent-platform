"""平台注入的文件及模型访问接口；业务契约不携带运行路径。"""
from types import MappingProxyType
from ..contracts.files import FileReference
from ..contracts.errors import ErrorResponse, PlatformError


class BlockContext:
    def __init__(self, *, files=None, run_id=None, models=None, progress=None):
        self._files, self._run_id = files, run_id
        self._models = MappingProxyType(dict(models or {}))
        self._progress = progress or (lambda event: None)

    def progress(self, message, *, current=None, total=None):
        self._progress({'message': str(message), 'current': current, 'total': total})

    def file(self, reference: FileReference):
        if self._files is None or self._run_id is None:
            raise PlatformError(ErrorResponse(code='FILE_NOT_FOUND', stage='block.context', message='任务文件上下文不可用'))
        return self._files.resolve(reference, run_id=self._run_id)

    def model(self, name: str):
        if name not in self._models:
            raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage='block.context', message='声明的模型文件未就绪'))
        return self._models[name]
