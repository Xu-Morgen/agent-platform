async def invoke(value, config, context):
    return await context.call_capability('identity', value)
