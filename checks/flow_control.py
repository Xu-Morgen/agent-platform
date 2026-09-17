import asyncio
from flow_execution import fixture, context, bind, ref
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.errors import PlatformError
from agent_platform.flows.execution import compile_flow
from agent_platform.runtime.context import current_context
from agent_platform.runtime.boundary import Boundary, current_boundary
from agent_platform.runtime.budgets import LoopPolicy
from agent_platform.runtime.cancellation import CancellationPolicy

async def main():
    app, original, env = fixture()
    doc = original.model_dump(by_alias=True)
    convert, package, _ = doc['flow']
    port = app.state.catalog.get(package['artifactRef']).output_contract
    package['inputs'] = bind({'kind': 'carry', 'nodeId': 'loop'})
    doc['flow'] = [convert, {'nodeId': 'loop', 'kind': 'repeat', 'count': 3,
        'carry': {'contract': port, 'initial': bind(ref('convert')), 'update': bind(ref('generate'))}, 'body': [package]}]
    doc.update(outputContract=port, output=bind(ref('loop')))
    draft = FlowDraft.model_validate(doc)
    ctx = context(app, original, env)
    ctx.runs.update(ctx.run_id, status='running')
    events = []
    bt = current_boundary.set(Boundary(policies=[CancellationPolicy(ctx.runs, ctx.run_id), LoopPolicy(ctx.run_id, ctx.snapshot, ctx.runs)], observer=lambda p,n: events.append((p,n))))
    ct = current_context.set(ctx)
    try:
        graph = compile_flow(draft, app.state.catalog)
        await graph.run({'legacyText': '合成'})
        assert ctx.runs.get(ctx.run_id).usage['loops']['global'] == 3
        steps = [s for s in ctx.runs.get(ctx.run_id).steps if s.kind == 'package']
        assert [s.execution_path for s in steps] == [['loop[0]'], ['loop[1]'], ['loop[2]']]
        try: await graph.run({'legacyText': '合成'}, recursion_limit=2)
        except PlatformError as exc: assert exc.error.code == 'GRAPH_EXECUTION_LIMIT'
        else: raise AssertionError()
        class Broken:
            async def invoke(self, *args): raise PlatformError(__import__('agent_platform.contracts.errors', fromlist=['ErrorResponse']).ErrorResponse(code='MODEL_TRANSPORT_ERROR', stage='model', message='合成错误'))
        before = ctx.runs.get(ctx.run_id).usage['loops']['global']
        ctx.model = Broken()
        try: await graph.run({'legacyText': '合成'})
        except PlatformError as exc: assert exc.error.code == 'MODEL_TRANSPORT_ERROR'
        else: raise AssertionError()
        assert ctx.runs.get(ctx.run_id).usage['loops']['global'] == before + 1
        started, release, stopped = asyncio.Event(), asyncio.Event(), asyncio.Event()
        class Inflight:
            async def invoke(self, *args):
                started.set()
                try:
                    await release.wait()
                    from flow_execution import SyntheticModel
                    return await SyntheticModel().invoke(*args)
                finally:
                    stopped.set()
        ctx.model = Inflight()
        task = asyncio.create_task(graph.run({'legacyText': '在途'}))
        await started.wait()
        ctx.runs.update(ctx.run_id, cancel_requested=True)
        await asyncio.sleep(0)
        assert not task.done() and not stopped.is_set()
        release.set()
        try: await task
        except PlatformError as exc: assert exc.error.code == 'RUN_CANCELLED'
        else: raise AssertionError()
        ctx.runs.update(ctx.run_id, cancel_requested=False)
        started.clear(); release.clear(); stopped.clear()
        task = asyncio.create_task(graph.run({'legacyText': '退出'}))
        await started.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert stopped.is_set()
        # 纯块空循环仍协作让出事件循环，并可在边界取消。
        doc['flow'] = [convert, {'nodeId': 'loop', 'kind': 'repeat', 'count': 100000,
            'carry': {'contract': port, 'initial': bind(ref('convert')), 'update': bind({'kind': 'carry', 'nodeId': 'loop'})}, 'body': []}]
        async def observer(phase, node):
            if phase == 'edge' and node == 'loop': ctx.runs.update(ctx.run_id, cancel_requested=True)
        current_boundary.get().observer = observer
        try: await compile_flow(FlowDraft.model_validate(doc), app.state.catalog).run({'legacyText': '合成'})
        except PlatformError as exc: assert exc.error.code == 'RUN_CANCELLED'
        else: raise AssertionError()
    finally:
        current_context.reset(ct); current_boundary.reset(bt)
    assert ('cleanup', 'flow') in events
    print('flow control: OK (累计三轮、失败计轮、循环路径、纯块取消、独立步数、清理)')

asyncio.run(main())
