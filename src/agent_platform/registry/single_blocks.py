"""从固定字节导入单文件块；仅导入声明，不执行注册业务函数。"""
import ast
import inspect
import sys
from pathlib import Path
from hashlib import sha256
from types import MappingProxyType
from uuid import uuid4
from typing import get_type_hints
from dataclasses import dataclass
from importlib.metadata import packages_distributions, version
from packaging.requirements import Requirement
from .snapshots import ContentSnapshot, _MemoryFinder
from .validation import invalid
from ..blocks.single import strict_adapter
from ..contracts.errors import PlatformError


@dataclass(frozen=True)
class SingleBlockArtifact:
    metadata_json: str
    content: ContentSnapshot
    entry: object
    input_adapter: object
    output_adapter: object

    @property
    def metadata(self):
        from ..blocks.single import BlockMetadata
        return BlockMetadata.model_validate_json(self.metadata_json)

    async def invoke(self, value, *, api=None):
        from pydantic import ValidationError
        from ..validation_issues import validation_exception
        try:
            parsed = self.input_adapter.validate_python(value, strict=True)
        except ValidationError as exc:
            raise validation_exception(exc, stage='block.input') from None
        if self.metadata.uses_api and api is None:
            raise invalid('API 通用块需要节点连接配置及任务上下文', ['api'])
        result = self.entry(parsed, api=api) if self.metadata.uses_api else self.entry(parsed)
        if inspect.isawaitable(result):
            result = await result
        try:
            return self.output_adapter.validate_python(result, strict=True)
        except ValidationError as exc:
            raise validation_exception(exc, stage='block.output', code='OUTPUT_VALIDATION_ERROR') from None


def capture_file(path):
    path = Path(path)
    if path.suffix != '.py' or path.is_symlink():
        raise invalid('请选择单个非符号链接 Python 文件', ['path'])
    source = path.read_bytes()
    digest = sha256(source).hexdigest()
    snapshot = ContentSnapshot(digest, f'_agent_block_{digest}_{uuid4().hex}', MappingProxyType({'block.py': source}))
    sys.meta_path.insert(0, _MemoryFinder(snapshot))
    return snapshot


class SingleBlockRegistry:
    def __init__(self):
        self._items = {}

    def load(self, path):
        content = None
        try:
            content = capture_file(path)
            tree = ast.parse(content.files['block.py'])
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level:
                        raise invalid('单文件块不能相对导入未快照的自有源码', ['imports'])
                    imports.add(node.module.split('.')[0])
                elif isinstance(node, ast.Import):
                    imports.update(alias.name.split('.')[0] for alias in node.names)
            installed = packages_distributions()
            for module in imports - sys.stdlib_module_names - {'agent_platform'}:
                if module not in installed:
                    raise invalid(f'未安装或未快照的导入模块：{module}', ['imports'], code='DEPENDENCY_ERROR')
            module = __import__(content.namespace + '.block', fromlist=['*'])
            functions = {id(fn): fn for fn in vars(module).values() if inspect.isfunction(fn) and hasattr(fn, '__block_metadata__') and fn.__module__ == module.__name__}
            if len(functions) != 1:
                raise invalid('单文件必须恰有一个注册业务函数', ['entry'])
            fn = next(iter(functions.values()))
            metadata = fn.__block_metadata__
            declared = set()
            for raw in metadata.dependencies:
                requirement = Requirement(raw)
                if requirement.marker and not requirement.marker.evaluate():
                    continue
                if requirement.url or requirement.extras or version(requirement.name) not in requirement.specifier:
                    raise invalid(f'依赖版本不满足：{requirement.name}', ['dependencies'], code='DEPENDENCY_ERROR')
                declared.add(requirement.name.lower().replace('_', '-'))
            for module_name in imports - sys.stdlib_module_names - {'agent_platform', 'pydantic'}:
                if not any(name.lower().replace('_', '-') in declared for name in installed[module_name]):
                    raise invalid(f'请声明第三方依赖：{module_name}', ['dependencies'], code='DEPENDENCY_ERROR')
            parameters = list(inspect.signature(fn).parameters.values())
            hints = get_type_hints(fn, include_extras=True)
            from ..blocks.api import BlockAPI
            expected = 2 if metadata.uses_api else 1
            if (len(parameters) != expected or parameters[0].kind not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                    or parameters[0].default is not inspect.Parameter.empty
                    or set(hints) != {parameters[0].name, 'return', *(['api'] if metadata.uses_api else [])}):
                raise invalid('块须有一个无默认值的输入参数及返回注解；API 块另声明关键字参数 api: BlockAPI', ['entry'])
            if metadata.uses_api and (parameters[1].name != 'api' or parameters[1].kind != inspect.Parameter.KEYWORD_ONLY
                    or parameters[1].default is not inspect.Parameter.empty or hints['api'] is not BlockAPI
                    or not inspect.iscoroutinefunction(fn)):
                raise invalid('API 块须为 async 函数并声明无默认值的关键字参数 api: BlockAPI', ['entry'])
            artifact = SingleBlockArtifact(metadata.model_dump_json(), content, fn,
                strict_adapter(hints[parameters[0].name]), strict_adapter(hints['return']))
            key = (metadata.id, metadata.version)
            existing = self._items.get(key)
            if existing:
                if existing.content.digest != content.digest:
                    raise invalid('同一块版本已有不同内容', ['version'], code='VERSION_CONFLICT')
                content.close()
                return existing
            self._items[key] = artifact
            return artifact
        except PlatformError:
            if content:
                content.close()
            raise
        except (ImportError, FileNotFoundError) as exc:
            if content:
                content.close()
            reason = getattr(exc, 'name', None)
            raise invalid(f'源码或代码依赖不可用{": " + reason if reason else ""}', ['path'], code='DEPENDENCY_ERROR') from None
        except Exception:
            if content:
                content.close()
            raise invalid('块声明、函数签名或严格契约无效', ['entry']) from None
