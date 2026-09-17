import asyncio
from dataclasses import replace
from services import setup_app
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.runtime.boundary import Boundary
from agent_platform.runtime.worker import RunWorker
from agent_platform.runtime.graphs import build_sequential
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.errors import PlatformError
from langgraph.errors import GraphRecursionError

async def case(limit):
    app, body = setup_app()
    body['definition']['budget'] = {'loopLimit': limit, 'tokenLimit': 200}
    svc = app.state.services.save(ServiceWrite.model_validate(body))
    run = app.state.submission.submit(RunSubmit(service_id=svc.service_id,input={'text':'合成'}))
    pending = await app.state.submission.queue.get()
    original = pending.snapshot
    class Entry:
        def load(self, ref):
            if ref == original.definition.entry:
                async def entry(value, context):
                    class State(StrictModel):
                        text: str
                    async def first(state):
                        return (await context.invoke_package('echo', {'text':state.text})).model_dump()
                    async def second(state):
                        return (await context.invoke_package('second', {'text':state.text})).model_dump()
                    return await build_sequential(State, [('first', first), ('second', second)]).run(value.model_dump(), boundary=Boundary())
                return entry
            return original.content.load(ref)
    events = []
    worker = RunWorker(app.state.submission, lambda: Boundary(observer=lambda phase, step: events.append(phase)))
    await worker.execute(replace(pending, snapshot=replace(original, content=Entry())))
    result = app.state.runs.get(run.run_id)
    assert result.status == ('completed' if limit == 2 else 'failed'), result.error
    if limit == 1:
        assert result.error.code == 'LOOP_BUDGET_EXCEEDED' and result.result is None
    assert result.usage['loops']['global'] == limit and 'cleanup' in events

async def main():
    await case(1)
    await case(2)
    class State(StrictModel):
        text: str
    class Recursion:
        async def ainvoke(self, *args, **kwargs):
            raise GraphRecursionError('synthetic')
    graph = build_sequential(State, [('one', lambda s: {})])
    try:
        await replace(graph, graph=Recursion()).run({'text':'合成'})
    except PlatformError as exc:
        assert exc.error.code == 'GRAPH_EXECUTION_LIMIT'
    else:
        raise AssertionError()
    print('PASS: 两节点不能绕过 loop；最后一次调用可完成；失败执行清理；图限制独立报错（异常替身）')

asyncio.run(main())
