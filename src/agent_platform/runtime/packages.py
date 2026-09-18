"""平台标准入口：替换 Prompt 字段、调用一次模型、严格校验结果。"""
import json
import re
from ..contracts.base import StrictModel
from ..contracts.models import ModelRequest
from .validation import validate

_PLACEHOLDER = re.compile(r'\{\{\s*((?:input|parameters)(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}\}')


def prompt_fields(prompt):
    """只支持命名空间与对象字段路径，不求值表达式、过滤器或索引。"""
    remainder = _PLACEHOLDER.sub('', prompt)
    if '{{' in remainder or '}}' in remainder:
        raise ValueError('Prompt 占位符只支持 {{input.field}} 或 {{parameters.field}}')
    return [match.group(1).split('.') for match in _PLACEHOLDER.finditer(prompt)]


def render_prompt(prompt, value, parameters):
    data = {'input': value.model_dump(mode='json', by_alias=True),
            'parameters': parameters.model_dump(mode='json', by_alias=True)}
    def substitute(match):
        item = data
        for key in match.group(1).split('.'):
            item = item[key]
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, separators=(',', ':'))
    return _PLACEHOLDER.sub(substitute, prompt)


async def invoke_prompt(runtime, node_id, artifact, value):
    stage = 'packages.' + node_id
    manifest = artifact.manifest
    config = runtime.snapshot.draft.node_configurations[node_id]
    parsed = validate(artifact.content.load(manifest.contract_refs.input), value, stage + '.input')
    parameter_model = (artifact.content.load(manifest.contract_refs.configuration)
                       if manifest.contract_refs.configuration else StrictModel)
    parameters = validate(parameter_model, config.parameters, stage + '.configuration')
    prompt = render_prompt(artifact.content.read_resource(manifest.prompt).decode('utf-8'), parsed, parameters)
    output_model = artifact.content.load(manifest.contract_refs.output)
    request = ModelRequest(messages=[
        {'role': 'system', 'content': '根据用户消息中的任务返回 JSON，不输出 Markdown 或额外说明。输出必须符合以下 JSON Schema：\n'
         + json.dumps(output_model.model_json_schema(by_alias=True), ensure_ascii=False)},
        {'role': 'user', 'content': prompt},
    ], max_output_tokens=config.max_output_tokens)
    response = await runtime.call_model(node_id, request)
    return validate(output_model, response.output, stage + '.output')
