"""拼图资源目录及源码持久化；资源与环境、服务实例独立。"""
from dataclasses import dataclass
from hashlib import sha256
from pydantic import TypeAdapter
from .single_blocks import SingleBlockRegistry, capture_file
from .validation import invalid
from ..blocks.single import strict_adapter
from ..contracts.catalog import CatalogResource
from ..contracts.base import StrictModel
from ..contracts.budgets import NodeBudget
from ..contracts.errors import PlatformError


@dataclass(frozen=True)
class ContractResource:
    adapter: TypeAdapter
    identity: str

    @property
    def schema(self):
        schema = self.adapter.json_schema(by_alias=True)
        schema['x-contract-id'] = self.identity
        def custom(value):
            if isinstance(value, dict):
                return (str(value.get('type', '')).startswith('function-') or value.get('allow_inf_nan') is False
                        or any(custom(v) for v in value.values()))
            if isinstance(value, (list, tuple)):
                return any(custom(v) for v in value)
            return False
        if custom(self.adapter.core_schema):
            schema['x-runtime-contract'] = self.identity
        return schema


class ModuleCatalog:
    def __init__(self, packages, store=None):
        self.packages = packages
        self.blocks = SingleBlockRegistry()
        self._views = {}
        self._artifacts = {}
        self._contracts = {}
        self._contents = []
        from ..storage import MemoryStore
        self.store = store or MemoryStore()
        self._sources = {}
        from ..storage.sources import decode_source
        from ..contracts.catalog import CatalogLoad
        for resource_id, document in self.store.read('resources').items():
            request = CatalogLoad(kind=document['kind'], path='<stored-source>', symbol=document.get('symbol'))
            view = self._load(request, decode_source(document))
            if view.resource_id != resource_id:
                raise ValueError('持久资源标识与源码不一致')

    def close(self):
        for content in self._sources.values():
            content.close()

    def register_contract(self, resource_id, annotation):
        resource = ContractResource(strict_adapter(annotation), resource_id)
        self._contracts[resource_id] = resource
        return resource

    def contract(self, resource_id):
        if resource_id not in self._contracts:
            raise invalid('契约资源未加载', ['contract'], code='DEPENDENCY_ERROR')
        return self._contracts[resource_id]

    def artifact(self, resource_id):
        if resource_id not in self._artifacts:
            raise invalid('模块资源未加载', ['artifactRef'], code='DEPENDENCY_ERROR')
        return self._artifacts[resource_id]

    def get(self, resource_id):
        if resource_id not in self._views:
            raise invalid('资源未加载', ['resourceId'], code='RECORD_NOT_FOUND')
        return self._views[resource_id].model_copy(deep=True)

    def list(self):
        return [self.get(key) for key in sorted(self._views)]

    def load(self, request):
        from ..storage.sources import encode_source
        # 先在独立目录校验；持久化失败不得向当前目录发布半成功资源。
        from .packages import PackageRegistry
        candidate = ModuleCatalog(PackageRegistry())
        view = candidate._load(request)
        if view.resource_id in self._views:
            for source in candidate._sources.values():
                source.close()
            return self.get(view.resource_id)
        artifact = candidate._artifacts.get(view.resource_id)
        if artifact:
            registry = self.packages if view.kind == 'package' else self.blocks
            meta = artifact.manifest if view.kind == 'package' else artifact.metadata
            key = (meta.package_id if view.kind == 'package' else meta.id, meta.version)
            if key in registry._items and registry._items[key].content.digest != view.digest:
                artifact.content.close()
                raise invalid('同一资源版本已有不同内容', ['version'], code='VERSION_CONFLICT')
        content = candidate._sources[view.resource_id]
        document = encode_source(content, request.kind, request.symbol)
        try:
            self.store.write([('resources', view.resource_id, document)])
        except Exception:
            content.close()
            raise
        self._views.update(candidate._views)
        self._artifacts.update(candidate._artifacts)
        self._contracts.update(candidate._contracts)
        self._contents.extend(candidate._contents)
        self.packages._items.update(candidate.packages._items)
        self.blocks._items.update(candidate.blocks._items)
        self._sources[view.resource_id] = content
        return self.get(view.resource_id)

    def _load(self, request, captured=None):
        content = None
        try:
            if request.kind == 'contract':
                if not request.symbol:
                    raise invalid('契约文件需要指定 Python 类型 symbol', ['symbol'])
                content = captured or capture_file(request.path)
                annotation = content.load('block:' + request.symbol)
                resource_id = f'contract:{content.digest}:{request.symbol}'
                contract = self.register_contract(resource_id, annotation)
                view = CatalogResource(resource_id=resource_id, kind='contract', name=request.symbol,
                    version=content.digest, digest=content.digest, schemas={'value': contract.schema})
                self._contents.append(content)
            else:
                registry = self.packages if request.kind == 'package' else self.blocks
                artifact = registry.load_content(captured) if captured else registry.load(request.path)
                content = artifact.content
                meta = artifact.manifest if request.kind == 'package' else artifact.metadata
                identifier = meta.package_id if request.kind == 'package' else meta.id
                resource_id = f'{request.kind}:{identifier}:{meta.version}:{artifact.content.digest}'
                schemas, refs = {}, {}
                if request.kind == 'package':
                    annotations = {key: artifact.content.load(ref) if ref else StrictModel
                                   for key, ref in meta.contract_refs.model_dump().items()}
                else:
                    annotations = {'input': artifact.input_adapter, 'output': artifact.output_adapter}
                for direction, annotation in annotations.items():
                    ref = resource_id + ':' + direction
                    contract = ContractResource(annotation, ref) if isinstance(annotation, TypeAdapter) else ContractResource(strict_adapter(annotation), ref)
                    self._contracts[ref] = contract
                    schemas[direction] = contract.schema
                    refs[direction + '_contract'] = ref
                view = CatalogResource(resource_id=resource_id, kind=request.kind, name=meta.name,
                    description=meta.description, version=meta.version, digest=artifact.content.digest,
                    schemas=schemas, api_required=meta.uses_api if request.kind == 'block' else False,
                    budget_defaults=(meta.budget_defaults or NodeBudget()) if request.kind == 'package' else None, **refs)
                self._artifacts[resource_id] = artifact
            self._sources[resource_id] = content
            self._views[resource_id] = view
            return self.get(resource_id)
        except PlatformError:
            if content:
                content.close()
            raise
        except (ImportError, FileNotFoundError) as exc:
            if content:
                content.close()
            module = getattr(exc, 'name', None)
            raise invalid('源码或代码依赖不可用' + (f'：{module}' if module else ''), ['path'], code='DEPENDENCY_ERROR') from None
        except Exception:
            if content:
                content.close()
            raise invalid('资源声明或严格契约无效，请检查所选文件与 symbol', ['path']) from None
