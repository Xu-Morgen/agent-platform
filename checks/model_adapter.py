import asyncio
import json
from local_http import local_http
from agent_platform.adapters.ollama import OllamaAdapter, ModelCallError
from agent_platform.contracts.environments import Connection
from agent_platform.contracts.models import ModelRequest
from agent_platform.contracts.errors import PlatformError
from agent_platform.repositories.credentials import CredentialRepository

async def main():
    mode = 'valid'
    started, disconnected = asyncio.Event(), asyncio.Event()
    calls = []
    async def respond(head, body, reader):
        payload = json.loads(body)
        calls.append(payload)
        assert head.startswith(b'POST /api/chat ') and payload['stream'] is False
        assert payload['options']['num_predict'] == 32 and payload['format'] == 'json'
        if mode in ('timeout','close'):
            started.set()
            await reader.read()
            disconnected.set()
        response = {'done':True,'done_reason':'stop','message':{'role':'assistant','content':'{"text":"合成"}'},'prompt_eval_count':5,'eval_count':4}
        if mode == 'bad': response['message']['content'] = '```not-json```'
        if mode == 'truncated': response['done_reason'] = 'length'
        if mode == 'missing': del response['eval_count']
        if mode == 'wire': return 200, b'bad-json'
        return 200, response
    async with local_http(respond) as url:
        adapter = OllamaAdapter(CredentialRepository())
        conn = Connection(connection_id='model', kind='model', base_url=url, model='synthetic', timeout_seconds=0.1)
        req = ModelRequest(messages=[{'role':'user','content':'返回 JSON'}], max_output_tokens=32)
        result = await adapter.invoke(conn, req)
        assert result.output == {'text':'合成'} and result.usage.output_tokens == 4
        mode = 'missing'
        assert (await adapter.invoke(conn, req)).usage.quality == 'unsupported'
        for mode, code in [('bad','OUTPUT_VALIDATION_ERROR'), ('truncated','OUTPUT_VALIDATION_ERROR'), ('wire','OUTPUT_VALIDATION_ERROR'), ('timeout','MODEL_TIMEOUT')]:
            try: await adapter.invoke(conn, req)
            except PlatformError as exc:
                assert exc.error.code == code
                if isinstance(exc, ModelCallError): assert exc.usage.output_tokens == 4
            else: raise AssertionError()
        mode = 'close'
        started.clear(); disconnected.clear()
        conn.timeout_seconds = 10
        task = asyncio.create_task(adapter.invoke(conn, req))
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.wait_for(adapter.close(), 2)
        await asyncio.wait_for(disconnected.wait(), 2)
        assert isinstance(task.exception(), PlatformError) and task.exception().error.code == 'MODEL_TRANSPORT_ERROR'
        assert not adapter.transport._clients and len(calls) == 7
    print('Ollama 本地协议替身：JSON/缺 usage/畸形/截断/超时/在途关闭，失败用量保留通过；非真实模型验收')

asyncio.run(main())
