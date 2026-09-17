from agent_platform.runtime.graphs import build_sequential
from agent_platform.runtime.context import current_context
from .models import Message


async def first(state):
    result = await current_context.get().invoke_package('first', state)
    return {'text': result.text}


async def second(state):
    result = await current_context.get().invoke_package('second', state)
    return {'text': result.text}


def build_graph():
    return build_sequential(Message, [('first', first), ('second', second)])
