"""生成实例的实际 worker / HTTP 链路，远端模型使用本地协议服务。"""
import asyncio
import json
import httpx
from flow_execution import fixture, bind, ref
from local_http import local_http
from agent_platform.application import create_app
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.errors import PlatformError

async def pure_blocks():
    app, draft, _ = fixture()
    doc = draft.model_dump(by_alias=True)
    doc['flow'] = doc['flow'][:1]
    doc.update(outputContract=app.state.catalog.get(doc['flow'][0]['artifactRef']).output_contract,
               output=bind(ref('convert')), budget=None, nodeConfigurations={})
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            draft_doc = await client.post('/api/v1/drafts', json={'content': doc})
            bad = await client.post('/api/v1/runs', json={'serviceId': draft_doc.json()['draftId'], 'input': {'legacyText': '合成'}})
            assert bad.status_code == 404 and bad.json()['code'] == 'RECORD_NOT_FOUND'
            service = app.state.services.save(ServiceWrite(name='纯块', flow=FlowDraft.model_validate(doc)))
            run_ids = []
            for _ in range(2):
                response = await client.post('/api/v1/runs', json={'serviceId': service.service_id,
                    'expectedInstanceId': service.active_instance_id, 'input': {'legacyText': '合成'}})
                assert response.status_code == 202, response.text
                run_ids.append(response.json()['runId'])
            assert len(set(run_ids)) == 2
            await app.state.submission.queue.join()
            for run_id in run_ids:
                run = (await client.get('/api/v1/runs/' + run_id)).json()
                assert run['status'] == 'completed' and run['environmentSnapshot'] == [] and run['usage'] == {}
                assert any(s['output'] == {'text': '合成'} for s in run['steps'])
                result = (await client.get('/api/v1/runs/' + run_id + '/result')).json()
                assert result['result'] == {'text': '合成'}
    fresh = create_app()
    try: fresh.state.runs.get(run_ids[0])
    except PlatformError as exc: assert exc.error.code == 'RECORD_NOT_FOUND'
    else: raise AssertionError()

async def model_run(mode):
    started, release, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests = []
    async def responder(head, body, reader):
        requests.append(body)
        started.set()
        if mode in ('exit', 'timeout'):
            await reader.read()
            disconnected.set()
        else:
            await release.wait()
        if mode == 'disconnect': raise ConnectionError('合成断连')
        output = '{"text": 1}' if mode == 'bad_output' else '{"text": "合成模型"}'
        return 200, {'done': True, 'done_reason': 'stop', 'message': {'role': 'assistant', 'content': output}, 'prompt_eval_count': 2, 'eval_count': 3}
    async with local_http(responder) as url:
        app, draft, env = fixture()
        env_write = EnvironmentWrite(name='协议替身', connections=[{'connectionId': 'model', 'kind': 'model',
            'baseUrl': url, 'model': 'synthetic', 'timeoutSeconds': 0.2 if mode == 'timeout' else 3}])
        app.state.environments.save(env_write, env.environment_id)
        if mode in ('repeat', 'budget'):
            doc = draft.model_dump(by_alias=True)
            convert, package, assembly = doc['flow']
            port = app.state.catalog.get(package['artifactRef']).output_contract
            package['inputs'] = bind({'kind': 'carry', 'nodeId': 'loop'})
            assembly['inputs'][1]['source']['nodeId'] = 'loop'
            doc['flow'] = [convert, {'nodeId': 'loop', 'kind': 'repeat', 'count': 3,
                'carry': {'contract': port, 'initial': bind(ref('convert')), 'update': bind(ref('generate'))},
                'body': [package]}, assembly]
            if mode == 'budget': doc['nodeConfigurations']['generate']['budget']['loopLimit'] = 2
            draft = FlowDraft.model_validate(doc)
        service = app.state.services.save(ServiceWrite(name='模型实例', flow=draft))
        run = app.state.submission.submit(RunSubmit(service_id=service.service_id, input={'legacyText': '在途原文'}))
        app.state.worker.start()
        try:
            await asyncio.wait_for(started.wait(), 3)
            try: app.state.environments.save(env_write, env.environment_id)
            except PlatformError as exc: assert exc.error.code == 'ENVIRONMENT_IN_USE'
            else: raise AssertionError('在途环境被修改')
            # 在途期间新版本立即生效，但不改变既有任务实际内容。
            draft.node_configurations['generate'].parameters['maxOutputTokens'] = 8
            newer = app.state.services.save(ServiceWrite(name='新版本', flow=draft), service.service_id)
            try: app.state.submission.submit(RunSubmit(service_id=service.service_id,
                expected_instance_id=service.active_instance_id, input={'legacyText': '旧引用'}))
            except PlatformError as exc: assert exc.error.code == 'VERSION_CONFLICT'
            else: raise AssertionError()
            if mode in ('cancel', 'disconnect', 'timeout'):
                from agent_platform.runtime.cancellation import cancel_run
                waiting = cancel_run(app.state.submission, run.run_id)
                assert waiting.status == 'running' and waiting.cancel_phase == 'waiting_transport'
            if mode == 'exit':
                await app.state.worker.stop()
                await asyncio.wait_for(disconnected.wait(), 2)
            else:
                release.set()
                await asyncio.wait_for(app.state.submission.queue.join(), 4)
            result = app.state.runs.get(run.run_id)
            expected = {'success': 'completed', 'cancel': 'cancelled', 'exit': 'cancelled',
                        'disconnect': 'failed', 'bad_output': 'failed', 'timeout': 'failed',
                        'repeat': 'completed', 'budget': 'failed'}[mode]
            assert result.status == expected, result
            calls = 3 if mode == 'repeat' else 2 if mode == 'budget' else 1
            assert result.instance_id == service.active_instance_id and len(requests) == calls
            request = json.loads(requests[0]) if isinstance(requests[0], (str, bytes)) else requests[0]
            assert request['options']['num_predict'] == 64
            assert result.usage['loops']['global'] == calls
            assert not app.state.environments.get(env.environment_id).active_run_ids
            assert app.state.services.get(service.service_id) == newer
            if mode in ('success', 'repeat'):
                assert result.result == {'original': '在途原文', 'generated': '合成模型'}
                assert result.usage['tokens']['global']['totalTokens'] == 5 * calls
            else:
                assert result.result is None
                if mode == 'budget': assert result.error.code == 'LOOP_BUDGET_EXCEEDED'
                if mode == 'timeout': assert result.error.code == 'MODEL_TIMEOUT'
                if mode == 'disconnect': assert result.error.code == 'MODEL_TRANSPORT_ERROR'
                if mode == 'bad_output': assert result.error.code == 'OUTPUT_VALIDATION_ERROR'
            app.state.environments.save(env_write, env.environment_id)
        finally: await app.state.worker.stop()
    print('flow runs:', mode, 'OK')

async def main():
    await pure_blocks()
    for mode in ('success', 'repeat', 'budget', 'cancel', 'disconnect', 'timeout', 'bad_output', 'exit'):
        await model_run(mode)
    print('flow runs: OK (草稿拒绝、纯块无环境预算、无去重、HTTP 查询、在途快照与环境锁、失败无部分报告、重启清空)')

asyncio.run(main())
