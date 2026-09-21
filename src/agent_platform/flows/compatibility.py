"""保守 JSON Schema 可赋值判断；不能证明的约束拒绝，不做数据转换。"""


class Incompatible(ValueError):
    pass


def resolve(schema, root):
    seen = set()
    while '$ref' in schema:
        ref = schema['$ref']
        if not ref.startswith('#/$defs/') or ref in seen:
            raise Incompatible('无法静态解析契约引用')
        seen.add(ref)
        schema = {**root['$defs'][ref.split('/')[-1]], **{k: v for k, v in schema.items() if k != '$ref'}}
    return schema


def assignable(source, target, source_root=None, target_root=None, seen=None):
    if source.get('x-contract-id') and source.get('x-contract-id') == target.get('x-contract-id'):
        return
    sr = source if '$defs' in source else (source_root or source)
    tr = target if '$defs' in target else (target_root or target)
    pair = (source.get('$ref', id(source)), target.get('$ref', id(target)))
    seen = set() if seen is None else seen
    if pair in seen:
        return
    seen = seen | {pair}
    source, target = resolve(source, sr), resolve(target, tr)
    if target.get('x-runtime-contract') and source.get('x-runtime-contract') != target['x-runtime-contract']:
        raise Incompatible('入口含自定义校验，需相同契约或显式转换块')
    # 递归 JSON 等循环引用以引用对截断，约束仍在首次访问时检查。
    cosmetic = {'title', 'description', 'default', 'examples', '$defs', '$id', 'x-runtime-contract', 'x-contract-id', 'x-platform-knowledge'}
    supported = {'type', 'properties', 'required', 'additionalProperties', 'items', 'anyOf', 'enum', 'const',
                 'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'minLength', 'maxLength',
                 'minItems', 'maxItems', 'pattern', 'format', 'multipleOf'}
    for key in (source.keys() | target.keys()) - cosmetic - supported:
        raise Incompatible(f'无法静态证明约束 {key}，请使用明确契约转换块')
    # 空 Schema 是任意 JSON 值（例如检索参数中的 JsonValue）。
    # 仅接收端无约束时放行；无约束出口仍不能赋给具体类型入口。
    if not target.keys() - cosmetic:
        return
    if 'anyOf' in source:
        for variant in source['anyOf']:
            assignable(variant, target, sr, tr, seen)
        return
    if 'anyOf' in target:
        for variant in target['anyOf']:
            try:
                assignable(source, variant, sr, tr, seen)
                return
            except Incompatible:
                pass
        raise Incompatible('出口类型或可空性不满足入口任一类型')
    st, tt = source.get('type'), target.get('type')
    if not st or not tt or not (st == tt or st == 'integer' and tt == 'number'):
        raise Incompatible(f'类型不兼容：出口 {st or "未限定"}，入口 {tt or "未限定"}')
    sv = source.get('enum', [source['const']] if 'const' in source else None)
    tv = target.get('enum', [target['const']] if 'const' in target else None)
    if tv is not None and (sv is None or any(not any(type(x) is type(y) and x == y for y in tv) for x in sv)):
        raise Incompatible('出口枚举范围超出入口')
    for low, high in [('minLength', 'maxLength'), ('minItems', 'maxItems')]:
        if low in target and source.get(low, 0) < target[low] or high in target and source.get(high, float('inf')) > target[high]:
            raise Incompatible(f'出口范围不满足 {low}/{high}')
    for lower in (True, False):
        inclusive, exclusive = ('minimum', 'exclusiveMinimum') if lower else ('maximum', 'exclusiveMaximum')
        fallback = -float('inf') if lower else float('inf')
        def bound(schema):
            values = [(schema.get(inclusive, fallback), False), (schema.get(exclusive, fallback), True)]
            return sorted(values, key=lambda x: (x[0] if lower else -x[0], x[1]))[-1]
        s, t = bound(source), bound(target)
        if (s[0] < t[0] if lower else s[0] > t[0]) or s[0] == t[0] and t[1] and not s[1]:
            raise Incompatible('出口数值范围超出入口')
    for key in ('pattern', 'format', 'multipleOf'):
        if key in target and source.get(key) != target[key]:
            raise Incompatible(f'不能证明出口满足 {key} 约束')
    if st == 'object':
        sp, tp = source.get('properties', {}), target.get('properties', {})
        if not set(target.get('required', [])).issubset(source.get('required', [])):
            raise Incompatible('输出缺少接收方必填字段：' + '、'.join(sorted(set(target.get('required', [])) - set(source.get('required', [])))))
        sa, ta = source.get('additionalProperties', True), target.get('additionalProperties', True)
        if ta is False and (sa is not False or sp.keys() - tp.keys()):
            raise Incompatible('入口禁止出口的额外字段')
        if isinstance(ta, dict) and sa is True:
            raise Incompatible('出口额外字段类型未限定')
        if isinstance(sa, dict) and isinstance(ta, dict):
            assignable(sa, ta, sr, tr, seen)
        for name in tp.keys() - sp.keys():
            if sa is True:
                raise Incompatible('出口未限定的额外字段可能违反入口字段类型')
            if isinstance(sa, dict):
                assignable(sa, tp[name], sr, tr, seen)
        for name, value in sp.items():
            expected = tp.get(name, ta)
            if isinstance(expected, dict):
                assignable(value, expected, sr, tr, seen)
    elif st == 'array':
        assignable(source.get('items', {}), target.get('items', {}), sr, tr, seen)


def array_item_schema(schema, path):
    """仅沿确定且必需的对象字段定位数组；保留局部引用的定义。"""
    root = schema
    current = resolve(schema, root)
    for field in path:
        if current.get('type') != 'object' or field not in current.get('required', []):
            raise Incompatible('数组路径必须经过确定、非可空的必填对象字段')
        if field not in current.get('properties', {}):
            raise Incompatible('数组路径字段不存在')
        current = resolve(current['properties'][field], root)
    if current.get('type') != 'array' or not isinstance(current.get('items'), dict):
        raise Incompatible('所选字段必须是确定的数组；可空或不确定结构请先用通用块规范化')
    return {**current['items'], **({'$defs': root['$defs']} if '$defs' in root else {})}


def collection_schema(item_schema):
    # defs 置于文档根；元素的自定义校验身份仍留在 items 内。
    return {'type': 'object', 'properties': {'items': {'type': 'array',
            'items': {k: v for k, v in item_schema.items() if k != '$defs'}}},
            'required': ['items'], 'additionalProperties': False,
            **({'$defs': item_schema['$defs']} if '$defs' in item_schema else {})}


def string_enum_values(schema):
    schema = resolve(schema, schema)
    values = schema.get('enum', [schema['const']] if 'const' in schema else [])
    if schema.get('type') != 'string' or not values or any(type(value) is not str for value in values):
        raise Incompatible('switch 路由出口必须是有限字符串 Literal 或字符串枚举')
    return values
