"""运行：.venv/bin/python examples/workflow/two_nodes.py。"""
import asyncio
from pydantic import Field
from agent_platform.contracts import StrictModel
from agent_platform.runtime import build_sequential


class State(StrictModel):
    text: str
    events: list[str] = Field(default_factory=list)


def build_graph():
    def normalize(state: State):
        return {'text': state.text.strip(), 'events': [*state.events, 'normalized']}

    async def finish(state: State):
        return {'text': state.text.upper(), 'events': [*state.events, 'finished']}

    return build_sequential(State, [('normalize', normalize), ('finish', finish)])


if __name__ == '__main__':
    print(asyncio.run(build_graph().run({'text': ' example '})).model_dump_json(by_alias=True))
