async def run(value, context):
    state = await context.run_graph(value)
    return state.report
