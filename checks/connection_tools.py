"""连接工具 HTTP 边界验证；仅访问本地协议替身。"""
import asyncio
import json
import httpx
from local_http import local_http
from agent_platform.application import create_app


async def main():
    mode = 'ok'
    calls = []
    started = asyncio.Event()
    async def respond(head, body, reader):
        calls.append(head.split(b'\r\n')[0])
        assert b'authorization: bearer synthetic-key' in head.lower()
        if mode == 'wait':
            started.set()
            await reader.read()
        if mode == 'auth': return 401, {'error': 'synthetic-key'}
        if mode == 'bad-list': return 200, {'data': [{'id': 42}]}
        if head.startswith(b'GET /v1/models '):
            return 200, {'data': [] if mode == 'empty' else [{'id': 'b'}, {'id': 'a'}, {'id': 'a'}]}
        if head.startswith(b'GET /api/tags '): return 200, {'models': [{'name': 'local'}]}
        payload = json.loads(body)
        assert 'JSON' in payload['messages'][0]['content']
        if head.startswith(b'POST /api/chat '):
            assert payload['options']['num_predict'] == 256
            return 200, {'done': True, 'done_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"ok":true}'},
                         'prompt_eval_count': 8, 'eval_count': 4}
        assert head.startswith(b'POST /v1/chat/completions ')
        assert payload['max_tokens'] == 256 and payload['stream'] is False
        assert payload['response_format'] == {'type': 'json_object'}
        return 200, {'choices': [{'finish_reason': 'length' if mode == 'truncated' else 'stop',
            'message': {'role': 'assistant', 'content': '{"ok":false}' if mode == 'wrong' else '{"ok":true}'}}],
            'usage': {'prompt_tokens': 8, 'completion_tokens': 4}}

    app = create_app()
    async with local_http(respond) as url, httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        connection = {'connectionId': 'm', 'kind': 'model', 'baseUrl': url + '/v1/',
            'modelAdapter': 'openai-chat', 'credential': 'synthetic-key', 'outputTokenParameter': 'max_tokens'}
        async def request(action, **changes):
            return await client.post('/api/v1/connection-tools/' + action, json={'connection': {**connection, **changes}})
        response = await request('models')
        assert response.status_code == 200, response.text
        assert response.json()['models'] == ['a', 'b']
        assert not app.state.credentials._values
        assert (await request('test')).status_code == 422  # 发现允许未填模型，推理测试不允许。
        connection['model'] = 'synthetic'
        response = await request('test')
        assert response.status_code == 200 and response.json()['usage']['outputTokens'] == 4, response.text
        saved = (await client.post('/api/v1/environments', json={'name': '工具验证', 'connections': [connection]})).json()
        connection.pop('credential')
        connection['credentialRef'] = saved['connections'][0]['credentialRef']
        assert (await request('models')).status_code == 200
        assert len(app.state.credentials._values) == 1
        assert (await client.get('/api/v1/environments')).json() == [saved]
        for mode, action, code in [('auth', 'models', 'MODEL_TRANSPORT_ERROR'),
                ('bad-list', 'models', 'OUTPUT_VALIDATION_ERROR'),
                ('wrong', 'test', 'OUTPUT_VALIDATION_ERROR'), ('truncated', 'test', 'OUTPUT_VALIDATION_ERROR')]:
            response = await request(action)
            assert response.json()['code'] == code, response.text
            assert 'synthetic-key' not in response.text
            if mode == 'auth': assert response.json()['details']['httpStatus'] == 401
        mode = 'empty'
        assert (await request('models')).json()['models'] == []
        mode = 'ok'
        assert (await request('models', baseUrl=url, modelAdapter='ollama-chat')).json()['models'] == ['local']
        assert (await request('test', baseUrl=url, modelAdapter='ollama-chat')).status_code == 200
        before = len(calls)
        assert (await request('models', baseUrl='[https://invalid](https://invalid)')).status_code == 422
        assert (await request('models', kind='api')).status_code == 422
        assert (await request('models', credentialRef='missing')).status_code == 404
        assert len(calls) == before
        mode = 'wait'
        assert (await request('models', timeoutSeconds=0.05)).json()['code'] == 'MODEL_TIMEOUT'
        started.clear()
        pending = asyncio.create_task(request('test', timeoutSeconds=30))
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.wait_for(app.state.connection_tools.close(), 2)
        assert (await pending).json()['code'] == 'MODEL_TRANSPORT_ERROR'
        assert not app.state.connection_tools._active
    print('PASS: draft discovery, inference, credentials, both protocols, errors, timeout and in-flight shutdown')


asyncio.run(main())
