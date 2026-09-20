"""公共校验错误投影：不回显 input、原始 ctx 或任意自定义异常全文。"""
from .contracts.errors import ValidationIssue, ErrorResponse, PlatformError

REASONS = {
    'missing': '缺少必填字段', 'extra_forbidden': '不允许未知字段',
    'int_type': '期望整数', 'float_type': '期望数值', 'string_type': '期望字符串',
    'bool_type': '期望严格布尔值', 'list_type': '期望数组', 'dict_type': '期望对象',
    'model_type': '期望对象', 'model_attributes_type': '期望对象', 'json_invalid': 'JSON 格式无效',
    'greater_than': '数值必须大于下限', 'greater_than_equal': '数值不得小于下限',
    'less_than': '数值必须小于上限', 'less_than_equal': '数值不得超过上限',
    'string_too_short': '字符串长度不足', 'string_too_long': '字符串超过最大长度',
    'too_short': '集合元素数量不足', 'too_long': '集合元素数量超过上限',
    'string_pattern_mismatch': '字符串不符合规定格式', 'finite_number': '期望有限数值',
    'literal_error': '值不属于允许的枚举', 'union_tag_invalid': '未知的结构类型',
    'union_tag_not_found': '缺少结构类型标识',
}
# 仅公开项目已审阅的固定原因；业务校验不得插入输入值。
SAFE_CUSTOM_REASONS = frozenset({
    'nodeId 重复', 'if 条件必须是通用块', '参考列表不得重复绑定同一来源',
    '连接标识重复', '模型连接必须指定模型标识',
    '连接地址须为无认证信息和查询参数的 HTTP(S) URL',
    'API 路径须为连接下的相对路径，不包含查询字符串、片段或目录回退',
    '填写凭据或引用其中一种，凭据不得为空',
    'node/carry 引用必须声明 nodeId；input 不声明 nodeId', 'while 条件必须是通用块',
    '可用计量必须提供输入和输出计数',
})
LIMIT_KEYS = {
    'greater_than': 'gt', 'greater_than_equal': 'ge', 'less_than': 'lt', 'less_than_equal': 'le',
    'string_too_short': 'min_length', 'string_too_long': 'max_length',
    'too_short': 'min_length', 'too_long': 'max_length',
}


def issues_from_errors(errors, *, stage='configuration', prefix=(), node_id=None, code='CONTRACT_VALIDATION_ERROR'):
    issues = []
    for error in errors:
        kind = error['type']
        reason = REASONS.get(kind, '未满足自定义契约约束，请检查对应字段')
        message = error.get('msg', '').removeprefix('Value error, ')
        if kind == 'value_error' and message in SAFE_CUSTOM_REASONS:
            reason = message
        expected = None
        key = LIMIT_KEYS.get(kind)
        if key:
            limit = error.get('ctx', {}).get(key)
            if type(limit) in (int, float):
                expected = f'{key}={limit}'
                reason += f'（{expected}）'
        issues.append(ValidationIssue(code=code, stage=stage, reason=reason, reason_type=kind,
            expected=expected, field_path=[*prefix, *error['loc']], node_id=node_id))
    return issues


def validation_exception(exc, *, stage='configuration', prefix=(), node_id=None, code='CONTRACT_VALIDATION_ERROR', status=422):
    issues = issues_from_errors(exc.errors(), stage=stage, prefix=prefix, node_id=node_id, code=code)
    first = issues[0]
    return PlatformError(ErrorResponse(code=code, stage=stage, message=first.reason,
        field_path=first.field_path, node_id=node_id, issues=issues), status)
