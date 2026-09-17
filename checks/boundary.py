import asyncio
from agent_platform.contracts import StrictModel
from agent_platform.runtime.graphs import build_sequential
from agent_platform.runtime.boundary import Boundary

class State(StrictModel):
    count: int

async def main():
    events = []
    graph = build_sequential(State, [('a', lambda s: {'count':s.count+1}), ('b', lambda s: {'count':s.count+1})])
    observer = lambda phase, step: events.append((phase, step))
    assert (await graph.run({'count':0}, boundary=Boundary(observer=observer))).count == 2
    assert events == [('start','graph'), ('node_start','a'), ('node_update','a'), ('edge','a'), ('node_start','b'), ('node_update','b'), ('edge','b'), ('terminal','graph'), ('cleanup','graph')]
    def fail(phase, step):
        if phase == 'node_update': raise ValueError('合成策略拒绝')
    events.clear()
    try:
        await graph.run({'count':0}, boundary=Boundary([fail], observer))
        raise AssertionError()
    except ValueError: pass
    assert events[-1] == ('cleanup','graph') and ('node_start','b') not in events
    print('两节点开始、更新、边与终态均检查；注入策略异常仍清理通过')

asyncio.run(main())
