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
    def primary_adapter(self):
        from ..contracts.node_input import NodeInput, primary_annotation
        annotation = get_type_hints(self.entry, include_extras=True)[next(iter(inspect.signature(self.entry).parameters))]
        if isinstance(annotation, type) and issubclass(annotation, NodeInput):
            return strict_adapter(primary_annotation(annotation))
        return None

    @property
    def metadata(self):
        from ..blocks.single import BlockMetadata
        return BlockMetadata.model_validate_json(self.metadata_json)

    async def invoke(self, value, *, api=None, context=None):
        from pydantic import ValidationError
        from ..validation_issues import validation_exception
        if self.primary_adapter is None:
            raise invalid('旧裸输入资源不可执行；请升级为 NodeInput 并重新加载', ['input'])
        try:
            parsed = self.input_adapter.validate_python(value, strict=True)
        except ValidationError as exc:
            raise validation_exception(exc, stage='block.input') from None
        if self.metadata.uses_api and api is None:
            raise invalid('API 通用块需要节点连接配置及任务上下文', ['api'])
        kwargs = {'api': api} if self.metadata.uses_api else {}
        if 'context' in inspect.signature(self.entry).parameters:
            from ..blocks.context import BlockContext
            kwargs['context'] = context or BlockContext()
        result = self.entry(parsed, **kwargs)
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
    def __init__(self, *, local=False, manager=None):
        self._items = {}
        self.local = local
        self.manager = manager

    def load(self, path):
        return self.load_content(capture_file(path))

    def load_content(self, content, *, locked=None, operation=None):
        try:
            from .declarations import read_declaration
            declaration = read_declaration(content.files['block.py'])
            if not self.local:
                from ..preparation.manager import RuntimeManager
                from ..blocks.process import ProcessBlock
                self.manager = self.manager or RuntimeManager()
                environment = self.manager.prepare(declaration, locked=locked, operation=operation)
                artifact = ProcessBlock(content, declaration, self.manager, environment, operation=operation)
                key = (declaration.id, declaration.version)
                existing = self._items.get(key)
                if existing:
                    if existing.content.digest != content.digest:
                        raise invalid('同一块版本已有不同内容', ['version'], code='VERSION_CONFLICT')
                    content.close()
                    return existing
                self._items[key] = artifact
                return artifact
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
            if metadata != declaration:
                raise invalid('导入后的声明与静态声明不一致', ['entry'])
            declared = set()
            for raw in metadata.dependencies:
                requirement = Requirement(raw)
                if requirement.marker and not requirement.marker.evaluate():
                    continue
                if requirement.url or version(requirement.name) not in requirement.specifier:
                    raise invalid(f'依赖版本不满足：{requirement.name}', ['dependencies'], code='DEPENDENCY_ERROR')
                declared.add(requirement.name.lower().replace('_', '-'))
            for module_name in imports - sys.stdlib_module_names - {'agent_platform', 'pydantic'}:
                if not any(name.lower().replace('_', '-') in declared for name in installed[module_name]):
                    raise invalid(f'请声明第三方依赖：{module_name}', ['dependencies'], code='DEPENDENCY_ERROR')
            parameters = list(inspect.signature(fn).parameters.values())
            hints = get_type_hints(fn, include_extras=True)
            from ..blocks.api import BlockAPI
            from ..blocks.context import BlockContext
            capabilities = ({'api': BlockAPI} if metadata.uses_api else {})
            if 'context' in hints:
                capabilities['context'] = BlockContext
            expected = 1 + len(capabilities)
            if (len(parameters) != expected or parameters[0].kind not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                    or parameters[0].default is not inspect.Parameter.empty
                    or set(hints) != {parameters[0].name, 'return', *capabilities}):
                raise invalid('块须有一个无默认值的输入参数及返回注解；API 块另声明关键字参数 api: BlockAPI', ['entry'])
            for parameter in parameters[1:]:
                if (parameter.name not in capabilities or parameter.kind != inspect.Parameter.KEYWORD_ONLY
                        or parameter.default is not inspect.Parameter.empty or hints[parameter.name] is not capabilities[parameter.name]):
                    raise invalid('能力参数须为无默认值的关键字参数 api: BlockAPI 或 context: BlockContext', ['entry'])
            if metadata.uses_api and not inspect.iscoroutinefunction(fn):
                raise invalid('API 块须为 async 函数', ['entry'])
            from ..contracts.node_input import NodeInput, require_node_input
            annotation = hints[parameters[0].name]
            if isinstance(annotation, type) and issubclass(annotation, NodeInput):
                require_node_input(annotation)
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
        except SyntaxError as exc:
            content.close()
            raise invalid(f'已读取通用块文件，但 Python 语法错误（第 {exc.lineno or "未知"} 行）', ['path']) from None
        except (ImportError, FileNotFoundError) as exc:
            if content:
                content.close()
            reason = getattr(exc, 'name', None)
            raise invalid(f'源码或代码依赖不可用{": " + reason if reason else ""}', ['path'], code='DEPENDENCY_ERROR') from None
        except Exception:
            if content:
                content.close()
            raise invalid('块声明、函数签名或严格契约无效', ['entry']) from None
