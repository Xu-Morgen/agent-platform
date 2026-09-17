"""加载固定版本业务包并检查本地运行依赖，不自动安装依赖。"""
from dataclasses import dataclass
from importlib.metadata import version, PackageNotFoundError
import platform
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from pydantic import ValidationError
from ..contracts.packages import PackageManifest, PackageBudget
from .snapshots import ContentSnapshot, capture
from .validation import invalid, load_symbol, validation_error


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
        content = capture(directory)
        try:
            manifest = PackageManifest.model_validate_json(content.read_resource('package.json'))
            runtime = manifest.runtime_requirements
            try:
                compatible_python = platform.python_version() in SpecifierSet(runtime.python)
            except ValueError:
                raise invalid('Python 版本约束格式无效', ['runtimeRequirements', 'python'], code='DEPENDENCY_ERROR') from None
            if not compatible_python:
                raise invalid('当前 Python 版本不满足包声明', ['runtimeRequirements', 'python'], code='DEPENDENCY_ERROR')
            for index, dependency in enumerate(runtime.dependencies):
                path = ['runtimeRequirements', 'dependencies', index]
                try:
                    requirement = Requirement(dependency)
                except ValueError:
                    raise invalid('代码依赖声明格式无效', path, code='DEPENDENCY_ERROR') from None
                if requirement.marker and not requirement.marker.evaluate():
                    continue
                if requirement.url or requirement.extras:
                    raise invalid('首期不支持 URL/extras 依赖', path, code='DEPENDENCY_ERROR')
                try:
                    installed = version(requirement.name)
                except PackageNotFoundError:
                    raise invalid(f'缺少已安装代码依赖：{requirement.name}', path, code='DEPENDENCY_ERROR') from None
                if installed not in requirement.specifier:
                    raise invalid(f'代码依赖版本不满足声明：{requirement.name}', path, code='DEPENDENCY_ERROR')
            load_symbol(content, manifest.entry, ['entry'])
            for key, reference in manifest.contract_refs.model_dump().items():
                model = load_symbol(content, reference, ['contractRefs', key], model=True)
                if key == 'configuration' and not issubclass(model, PackageBudget):
                    raise invalid('包配置模型必须继承 PackageBudget', ['contractRefs', key])
            for i, capability in enumerate(manifest.required_capabilities):
                load_symbol(content, capability.input_model, ['requiredCapabilities', i, 'inputModel'], model=True)
                load_symbol(content, capability.output_model, ['requiredCapabilities', i, 'outputModel'], model=True)
            ids = [value.capability_id for value in manifest.required_capabilities]
            if len(set(ids)) != len(ids):
                raise invalid('能力标识重复', ['requiredCapabilities'])
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
            raise validation_error(exc) from None
        except Exception:
            content.close()
            raise

    def get(self, package_id, version):
        if (package_id, version) not in self._items:
            raise invalid('包版本未加载', ['packageBindings'], code='DEPENDENCY_ERROR')
        return self._items[package_id, version]
