"""共享契约身份：只归并公开结构足以描述的契约，不覆盖历史资源引用。"""
from hashlib import sha256
import json


def validation_shape(adapter):
    """比较 Schema 未表达的别名、默认处理和模型配置；无法证明时保持独立。"""
    if hasattr(adapter, 'validation_shape'):
        return adapter.validation_shape
    references = {}
    def visit(value):
        if isinstance(value, (list, tuple)):
            return [visit(item) for item in value]
        if isinstance(value, dict):
            if str(value.get('type', '')).startswith('function-') or value.get('post_init'):
                raise ValueError('custom validation')
            result = {}
            for key, item in sorted(value.items()):
                if key in {'cls', 'model_name', 'metadata'}:
                    continue
                if key in {'ref', 'schema_ref'}:
                    result[key] = references.setdefault(item, 'R' + str(len(references)))
                elif key == 'fields' and isinstance(item, dict):
                    result[key] = {name: visit(field) for name, field in sorted(item.items())}
                elif key == 'default':
                    # 默认对象是业务数据，不能把其键当作 core_schema 关键字。
                    result[key] = json.loads(json.dumps(item, sort_keys=True))
                elif key == 'config':
                    result[key] = visit({name: setting for name, setting in item.items() if name != 'title'})
                else:
                    result[key] = visit(item)
            return result
        if value is None or type(value) in (str, int, float, bool):
            return value
        raise ValueError('opaque validation')
    try:
        return visit(adapter.core_schema)
    except (ValueError, TypeError):
        return None


def canonical_schema(schema):
    definitions = schema.get('$defs', {})
    names, normalized = {}, {}

    def visit(value):
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key in sorted(value):
            item = value[key]
            if key in {'title', 'description', 'examples', 'x-contract-id', '$defs'}:
                continue
            if key == '$ref' and item.startswith('#/$defs/'):
                original = item[len('#/$defs/'):]
                if original not in names:
                    name = 'T' + str(len(names))
                    names[original] = name
                    normalized[name] = visit(definitions[original])
                result[key] = '#/$defs/' + names[original]
            elif key in {'properties', 'patternProperties', 'dependentSchemas'}:
                # 字段名与 Schema 关键字分开处理，不能删除名为 title/default 的业务字段。
                result[key] = {name: visit(field) for name, field in sorted(item.items())}
            elif key in {'default', 'const', 'enum'}:
                result[key] = item
            elif key == 'required':
                result[key] = sorted(item)
            else:
                result[key] = visit(item)
        return result

    result = visit(schema)
    if normalized:
        result['$defs'] = normalized
    return result


def contract_groups(catalog):
    from .catalog import ContractResource
    groups = {}
    for resource in catalog.list():
        entries = [('value', resource.resource_id)] if resource.kind == 'contract' else [
            ('primary', resource.primary_contract), ('output', resource.output_contract)]
        for direction, reference in entries:
            if not reference:
                continue
            contract = catalog.contract(reference)
            schema = contract.schema
            shape = validation_shape(contract.adapter)
            independent = bool(schema.get('x-runtime-contract')) or shape is None
            if independent:
                identity = reference
            else:
                digest = sha256(json.dumps({'schema': canonical_schema(schema), 'validation': shape}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                identity = 'shared:' + digest
            group = groups.setdefault(identity, {'contractId': identity, 'aliases': [], 'schema': {**schema, 'x-contract-id': identity},
                'sources': [], 'runtimeValidation': independent})
            group['aliases'].append(reference)
            group['sources'].append({'resourceId': resource.resource_id, 'kind': resource.kind, 'name': resource.name,
                                     'version': resource.version, 'direction': direction, 'archived': resource.archived})
            if identity not in catalog._contracts:
                catalog._contracts[identity] = ContractResource(contract.adapter, identity, canonical_schema(schema))
    return list(groups.values())
