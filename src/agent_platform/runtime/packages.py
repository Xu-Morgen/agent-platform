"""平台标准入口：替换 Prompt 字段、调用一次模型、严格校验结果。"""
import json
import re
from ..contracts.base import StrictModel
from ..contracts.models import ModelRequest
from ..contracts.errors import ErrorResponse, PlatformError
from .validation import validate

_PLACEHOLDER = re.compile(r'\{\{\s*((?:input|parameters)(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\])*)\s*\}\}')


def prompt_path(path):
    return [int(index) if index else name for name, index in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)|\[([0-9]+)\]', path)]


def prompt_fields(prompt):
    """只支持对象字段与固定数组索引，不求值表达式或过滤器。"""
    remainder = _PLACEHOLDER.sub('', prompt)
    if '{{' in remainder or '}}' in remainder:
        raise ValueError('Prompt 占位符只支持 {{input.primary.field}}、{{input.references[0]}} 或 {{parameters.field}}')
    return [prompt_path(match.group(1)) for match in _PLACEHOLDER.finditer(prompt)]


def render_prompt(prompt, value, parameters):
    data = {'input': value.model_dump(mode='json', by_alias=True),
            'parameters': parameters.model_dump(mode='json', by_alias=True)}
    def substitute(match):
        item = data
        for key in prompt_path(match.group(1)):
            item = item[key]
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, separators=(',', ':'))
    return _PLACEHOLDER.sub(substitute, prompt)


async def invoke_prompt(runtime, node_id, artifact, value):
    stage = 'packages.' + node_id
    manifest = artifact.manifest
    config = runtime.snapshot.draft.node_configurations[node_id]
    from ..contracts.node_input import require_node_input
    input_model = artifact.content.load(manifest.contract_refs.input)
    require_node_input(input_model)
    parsed = validate(input_model, value, stage + '.input')
    parameter_model = (artifact.content.load(manifest.contract_refs.configuration)
                       if manifest.contract_refs.configuration else StrictModel)
    parameters = validate(parameter_model, config.parameters, stage + '.configuration')
    prompt = render_prompt(artifact.content.read_resource(manifest.prompt).decode('utf-8'), parsed, parameters)
    output_model = artifact.content.load(manifest.contract_refs.output)
    request = ModelRequest(messages=[
        {'role': 'system', 'content': '根据用户消息中的任务返回 JSON，不输出 Markdown 或额外说明。资料不足以完成任务时仅返回 {"error":"INSUFFICIENT_INPUT"}。成功输出必须符合以下 JSON Schema：\n'
         + json.dumps(output_model.model_json_schema(by_alias=True), ensure_ascii=False)},
        {'role': 'user', 'content': prompt},
    ], max_output_tokens=config.max_output_tokens)
    response = await runtime.call_model(node_id, request)
    if response.output == {'error': 'INSUFFICIENT_INPUT'}:
        raise PlatformError(ErrorResponse(code='PACKAGE_INPUT_INSUFFICIENT', stage=stage,
                                          message='输入资料不足以完成本步骤，请补充资料后重新提交'))
    return validate(output_model, response.output, stage + '.output')
