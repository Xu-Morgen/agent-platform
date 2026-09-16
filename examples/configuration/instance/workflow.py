from agent_platform.runtime.graphs import build_sequential
from .models import Message

def build_graph():
    return build_sequential(Message, [('identity', lambda state: {'text': state.text})])
