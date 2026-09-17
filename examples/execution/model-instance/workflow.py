from agent_platform.runtime.graphs import build_sequential
from agent_platform.runtime.context import current_context
from .models import Message

async def invoke(state):
    result = await current_context.get().invoke_package('assistant', state)
    return {'text':result.text}

def build_graph():
    return build_sequential(Message, [('assistant', invoke)])
