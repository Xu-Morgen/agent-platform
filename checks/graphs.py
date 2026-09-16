import asyncio
import importlib.util
from pathlib import Path
from pydantic import ValidationError
from agent_platform.runtime import build_sequential

spec = importlib.util.spec_from_file_location('two_nodes', Path('examples/workflow/two_nodes.py'))
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)

async def main():
    executor = example.build_graph()
    data = {'text': ' first ', 'events': []}
    first, second = await asyncio.gather(executor.run(data), executor.run({'text': ' second '}))
    assert first.text == 'FIRST' and second.text == 'SECOND'
    assert first.events == second.events == ['normalized', 'finished']
    first.events.append('changed')
    assert 'changed' not in second.events and data['events'] == []
    assert executor.graph.checkpointer is None
    calls = 0
    def invalid(state):
        nonlocal calls
        calls += 1
        return {'text': 1}
    bad = build_sequential(example.State, [('bad', invalid)])
    try:
        await bad.run({'text': 'ok'})
    except ValidationError as e:
        assert e.errors()[0]['loc'] == ('text',)
    else:
        raise AssertionError('invalid state update accepted')
    assert calls == 1, 'automatic retry must remain disabled'
    for update in ({'unknown': 1}, 'not-a-dict'):
        bad = build_sequential(example.State, [('bad', lambda state: update)])
        try:
            await bad.run({'text': 'ok'})
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError('invalid update accepted')
    print('T13 PASS: real LangGraph two-node runs isolated, bad updates rejected, no retries/checkpointer')

asyncio.run(main())
