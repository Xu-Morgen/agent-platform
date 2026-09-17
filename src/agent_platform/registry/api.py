"""本地加载 API 适配层；错误仅返回固定原因与字段路径。"""
from pathlib import Path
from ..contracts.registry import LoadResult
from ..contracts.errors import PlatformError
from ..configuration import validate_combination
from .validation import invalid, load_symbol


def load_local(state, request):
    try:
        directory = Path(request.path)
        if directory.is_file():
            raise invalid('请选择定义所在的文件夹，不要选择 JSON 或 Python 文件', ['path'], code='DEPENDENCY_ERROR')
        if not directory.is_dir():
            raise invalid('本地目录不存在，请填写后端可访问的文件夹路径', ['path'], code='DEPENDENCY_ERROR')
        manifest = {'instance': 'instance.json', 'package': 'package.json', 'block': 'block.json'}[request.kind]
        if not (directory / manifest).is_file():
            raise invalid(f'所选文件夹缺少 {manifest}，请检查定义类型和目录层级', ['path'], code='DEPENDENCY_ERROR')
        if request.kind == 'instance':
            loaded = state.definitions.load(request.path)
            try:
                definition, _, _, scopes, defaults = validate_combination(
                    loaded.definition, loaded.content, state.packages, state.blocks, state.environments)
            except Exception:
                state.definitions._items.pop(loaded.load_id, None)
                loaded.content.close()
                raise
            schemas = {key: load_symbol(loaded.content, getattr(definition, key + '_model'), [key], model=True).model_json_schema() for key in ('input', 'output')}
            for binding in definition.package_bindings:
                artifact = state.packages.get(binding.package_id, binding.version)
                schemas['packages.' + binding.binding_id] = artifact.content.load(artifact.manifest.contract_refs.configuration).model_json_schema()
            return LoadResult(kind='instance', id=definition.definition_id, load_id=loaded.load_id,
                              digest=loaded.content.digest, definition=definition, schemas=schemas,
                              configuration=scopes, budget_defaults=defaults.model_dump(mode='json', by_alias=True))
        registry = state.packages if request.kind == 'package' else state.blocks
        artifact = registry.load(request.path)
        manifest = artifact.manifest
        references = manifest.contract_refs.model_dump() if request.kind == 'package' else {'input':manifest.input_model, 'output':manifest.output_model}
        return LoadResult(kind=request.kind, id=manifest.package_id if request.kind == 'package' else manifest.block_id,
                          version=manifest.version, digest=artifact.content.digest,
                          schemas={key: artifact.content.load(ref).model_json_schema() for key, ref in references.items()})
    except PlatformError:
        raise
    except (FileNotFoundError, NotADirectoryError):
        raise invalid('本地目录或声明文件不存在', ['path'], code='DEPENDENCY_ERROR') from None
    except Exception:
        raise invalid('无法加载本地定义，请检查文件、入口和已安装依赖', ['path'], code='DEPENDENCY_ERROR') from None
