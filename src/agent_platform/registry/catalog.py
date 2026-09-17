"""新拼图的会话资源目录；资源与环境、服务实例独立。"""
from dataclasses import dataclass
from hashlib import sha256
from pydantic import TypeAdapter
from .single_blocks import SingleBlockRegistry, capture_file
from .validation import invalid
from ..blocks.single import strict_adapter
from ..contracts.catalog import CatalogResource
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
    def __init__(self, packages):
        self.packages = packages
        self.blocks = SingleBlockRegistry()
        self._views = {}
        self._artifacts = {}
        self._contracts = {}
        self._contents = []

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
        content = None
        try:
            if request.kind == 'contract':
                if not request.symbol:
                    raise invalid('契约文件需要指定 Python 类型 symbol', ['symbol'])
                content = capture_file(request.path)
                annotation = content.load('block:' + request.symbol)
                resource_id = f'contract:{content.digest}:{request.symbol}'
                contract = self.register_contract(resource_id, annotation)
                view = CatalogResource(resource_id=resource_id, kind='contract', name=request.symbol,
                    version=content.digest, digest=content.digest, schemas={'value': contract.schema})
                self._contents.append(content)
            else:
                artifact = self.packages.load(request.path) if request.kind == 'package' else self.blocks.load(request.path)
                meta = artifact.manifest if request.kind == 'package' else artifact.metadata
                identifier = meta.package_id if request.kind == 'package' else meta.id
                resource_id = f'{request.kind}:{identifier}:{meta.version}:{artifact.content.digest}'
                schemas, refs = {}, {}
                if request.kind == 'package':
                    annotations = {key: artifact.content.load(ref) for key, ref in meta.contract_refs.model_dump().items()}
                else:
                    annotations = {'input': artifact.input_adapter, 'output': artifact.output_adapter}
                for direction, annotation in annotations.items():
                    ref = resource_id + ':' + direction
                    contract = ContractResource(annotation, ref) if isinstance(annotation, TypeAdapter) else ContractResource(strict_adapter(annotation), ref)
                    self._contracts[ref] = contract
                    schemas[direction] = contract.schema
                    refs[direction + '_contract'] = ref
                capabilities = []
                if request.kind == 'package':
                    for requirement in meta.required_capabilities:
                        item = requirement.model_dump(mode='json', by_alias=True)
                        for direction in ('input', 'output'):
                            ref = resource_id + ':capability:' + requirement.capability_id + ':' + direction
                            contract = self.register_contract(ref, artifact.content.load(getattr(requirement, direction + '_model')))
                            item[direction + 'Contract'] = ref
                            item[direction + 'Schema'] = contract.schema
                        capabilities.append(item)
                view = CatalogResource(resource_id=resource_id, kind=request.kind, name=meta.name,
                    description=meta.description, version=meta.version, digest=artifact.content.digest,
                    schemas=schemas, required_capabilities=capabilities,
                    budget_defaults=meta.budget_defaults if request.kind == 'package' else None, **refs)
                self._artifacts[resource_id] = artifact
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
