"""受信任源码的会话内内容快照；这不是第三方代码沙箱。"""
from dataclasses import dataclass
from hashlib import sha256
import importlib
import importlib.abc
import importlib.util
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping
import sys
from uuid import uuid4


class _MemoryLoader(importlib.abc.Loader):
    def __init__(self, snapshot: 'ContentSnapshot', source: str | None):
        self.snapshot = snapshot
        self.source = source

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if self.source is not None:
            filename = f'<{self.snapshot.namespace}/{self.source}>'
            module.__file__ = filename
            exec(compile(self.snapshot.files[self.source], filename, 'exec'), module.__dict__)


class _MemoryFinder(importlib.abc.MetaPathFinder):
    def __init__(self, snapshot: 'ContentSnapshot'):
        self.snapshot = snapshot

    def find_spec(self, fullname, path=None, target=None):
        root = self.snapshot.namespace
        if fullname != root and not fullname.startswith(root + '.'):
            return None
        relative = fullname[len(root):].lstrip('.').replace('.', '/')
        prefix = relative + '/' if relative else ''
        package_file = prefix + '__init__.py'
        module_file = relative + '.py'
        if package_file in self.snapshot.files:
            source, package = package_file, True
        elif relative and module_file in self.snapshot.files:
            source, package = module_file, False
        elif not relative or any(name.startswith(prefix) for name in self.snapshot.files):
            source, package = None, True
        else:
            raise ModuleNotFoundError(f'快照中不存在模块：{fullname}', name=fullname)
        return importlib.util.spec_from_loader(fullname, _MemoryLoader(self.snapshot, source), is_package=package)


@dataclass(frozen=True)
class ContentSnapshot:
    digest: str
    namespace: str
    files: Mapping[str, bytes]

    def read_resource(self, name: str) -> bytes:
        """平台入口从快照读取 Prompt；不使用原始目录或 __file__。"""
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('资源必须使用规范的快照相对路径')
        return self.files[name]

    def load(self, reference: str) -> Any:
        """解析 module:Symbol；自有模块须使用相对导入保持命名空间隔离。"""
        from ..contracts.packages import SymbolReference
        from pydantic import TypeAdapter
        TypeAdapter(SymbolReference).validate_python(reference, strict=True)
        module, symbol = reference.split(':')
        loaded = importlib.import_module(f'{self.namespace}.{module}')
        return getattr(loaded, symbol)

    def close(self) -> None:
        """仅在不再有使用者时释放导入注册；已有对象不会被替换。"""
        sys.meta_path[:] = [finder for finder in sys.meta_path if not (isinstance(finder, _MemoryFinder) and finder.snapshot is self)]
        for name in list(sys.modules):
            if name == self.namespace or name.startswith(self.namespace + '.'):
                del sys.modules[name]


def capture(directory: str | Path) -> ContentSnapshot:
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('快照来源必须是目录')
    files = {}
    ignored = {'__pycache__', '.git', '.venv', 'node_modules'}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if ignored.intersection(relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f'快照不接受符号链接：{relative.as_posix()}')
        if path.is_file():
            files[relative.as_posix()] = path.read_bytes()
    if not files:
        raise ValueError('快照来源为空')
    digest = sha256()
    for name, content in files.items():
        encoded = name.encode('utf-8')
        digest.update(len(encoded).to_bytes(8, 'big'))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    hexdigest = digest.hexdigest()
    # 同内容的不同加载也隔离模块全局变量；摘要仍稳定反映全部内容。
    snapshot = ContentSnapshot(hexdigest, f'_agent_snapshot_{hexdigest}_{uuid4().hex}', MappingProxyType(files))
    sys.meta_path.insert(0, _MemoryFinder(snapshot))
    return snapshot
