from .models import ModelRequest


async def invoke(value, config, context):
    response = await context.call_model('chat', ModelRequest(messages=[
        {'role':'system', 'content':context.read_resource('prompt.txt').decode('utf-8') + '\n' + config.instruction},
        {'role':'user', 'content':value.text},
    ], max_output_tokens=config.max_output_tokens))
    return response.output
