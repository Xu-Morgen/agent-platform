from .models import ModelRequest

async def invoke(value, config, context):
    result = await context.call_model('chat', ModelRequest(
        messages=[{'role':'user','content':'请以 JSON 对象 text 字段回复：' + value.text}],
        max_output_tokens=config.max_output_tokens))
    return result.output
