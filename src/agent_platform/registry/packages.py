"""加载固定版本的声明式 Prompt 包；无业务入口或包依赖安装。"""
from dataclasses import dataclass
from pydantic import ValidationError
from ..contracts.base import StrictModel
from ..contracts.packages import PackageManifest
from ..runtime.packages import prompt_fields
from .snapshots import ContentSnapshot, capture
from .validation import invalid, load_model, validation_error


@dataclass(frozen=True)
class PackageArtifact:
    manifest_json: str
    content: ContentSnapshot

    @property
    def manifest(self):
        return PackageManifest.model_validate_json(self.manifest_json)


class PackageRegistry:
    def __init__(self):
        self._items = {}

    def load(self, directory):
        return self.load_content(capture(directory))

    def load_content(self, content):
        try:
            manifest = PackageManifest.model_validate_json(content.read_resource('package.json'))
            models = {key: load_model(content, reference, ['contractRefs', key])
                      for key, reference in manifest.contract_refs.model_dump().items() if reference}
            try:
                prompt = content.read_resource(manifest.prompt).decode('utf-8')
                if not prompt.strip():
                    raise ValueError('Prompt 不能为空')
                fields = prompt_fields(prompt)
            except (KeyError, ValueError):
                raise invalid('Prompt 文件不可用或占位符无效', ['prompt']) from None
            for path in fields:
                model = models.get('input' if path[0] == 'input' else 'configuration', StrictModel)
                schema = model.model_json_schema(by_alias=True)
                current = schema
                for key in path[1:]:
                    if '$ref' in current:
                        current = schema['$defs'][current['$ref'].split('/')[-1]]
                    current = (current.get('prefixItems', [])[key] if isinstance(key, int) and key < len(current.get('prefixItems', []))
                               else current.get('properties', {}).get(key) if isinstance(key, str) else None)
                    if current is None:
                        raise invalid('Prompt 字段不存在或不是可直接访问的对象字段：' + '.'.join(map(str, path)), ['prompt'])
            key = (manifest.package_id, manifest.version)
            existing = self._items.get(key)
            if existing:
                if existing.content.digest != content.digest:
                    raise invalid('同一包版本已有不同内容', ['version'], code='VERSION_CONFLICT')
                content.close()
                return existing
            artifact = PackageArtifact(manifest.model_dump_json(), content)
            self._items[key] = artifact
            return artifact
        except ValidationError as exc:
            content.close()
            raise validation_error(exc, prefix=('package.json',)) from None
        except Exception:
            content.close()
            raise

    def get(self, package_id, version):
        if (package_id, version) not in self._items:
            raise invalid('包版本未加载', ['packageBindings'], code='DEPENDENCY_ERROR')
        return self._items[package_id, version]
