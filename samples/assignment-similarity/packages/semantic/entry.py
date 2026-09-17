import json
from .models import ModelRequest, QualitativeReport


async def invoke(value, config, context):
    response = await context.call_model('chat', ModelRequest(
        messages=[
            {'role': 'system', 'content': context.read_resource('prompt.txt').decode('utf-8')},
            {'role': 'user', 'content': json.dumps(value.model_dump(by_alias=True), ensure_ascii=False)},
        ], max_output_tokens=config.max_output_tokens))
    # 一次交互，不修复或重试错误结果；必须按本次输入覆盖全部对照。
    return QualitativeReport.model_validate(response.output,
        context={'comparison_count': len(value.comparison_texts)})
