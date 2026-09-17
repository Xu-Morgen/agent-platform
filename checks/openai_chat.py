"""OpenAI 兼容协议定向验证，全部使用本地 HTTP 替身。"""
import asyncio
import json
from pydantic import SecretStr
from local_http import local_http
from agent_platform.adapters.openai_chat import OpenAIChatAdapter
from agent_platform.contracts.environments import Connection
from agent_platform.contracts.models import ModelRequest
from agent_platform.contracts.errors import PlatformError
from agent_platform.repositories.credentials import CredentialRepository
from similarity_support import ROOT, configure, execute, qualitative


def completion(output):
    return {'choices':[{'finish_reason':'stop','message':{'role':'assistant',
        'content':json.dumps(output)}}], 'usage':{'prompt_tokens':32,'completion_tokens':16,
        'total_tokens':48,'completion_tokens_details':{'reasoning_tokens':4}}}


async def main():
    mode = 'success'
    calls = []
    started, disconnected = asyncio.Event(), asyncio.Event()
    async def respond(head, body, reader):
        payload = json.loads(body)
        calls.append(payload)
        assert head.startswith(b'POST /v1/chat/completions ')
        assert b'authorization: bearer local-test-key' in head.lower()
        assert payload['stream'] is False
        if mode == 'legacy':
            assert payload['max_tokens'] == 64 and 'max_completion_tokens' not in payload
            assert 'response_format' not in payload
        else:
            assert payload['max_completion_tokens'] == 64 and 'max_tokens' not in payload
            assert payload['response_format'] == {'type':'json_object'}
        data = completion({'text':'替身'})
        if mode in ('timeout','close'):
            started.set()
            await reader.read()
            disconnected.set()
        if mode == 'http': return 401, {'error':{'message':'secret upstream'}}
        if mode == 'missing': data.pop('usage')
        if mode == 'bad-usage': data['usage']['prompt_tokens'] = True
        if mode == 'bad-total': data['usage']['total_tokens'] = 99
        if mode == 'truncated': data['choices'][0]['finish_reason'] = 'length'
        if mode == 'refused': data['choices'][0]['message']['refusal'] = '拒绝'
        if mode == 'bad-json': data['choices'][0]['message']['content'] = '```json```'
        if mode == 'nan': data['choices'][0]['message']['content'] = '{"n":NaN}'
        return 200, data
    credentials = CredentialRepository()
    ref = credentials.put(SecretStr('local-test-key')).credential_ref
    async with local_http(respond) as url:
        adapter = OpenAIChatAdapter(credentials)
        connection = Connection(connection_id='model',kind='model',base_url=url+'/v1/',model='synthetic',
                                model_adapter='openai-chat',credential_ref=ref,timeout_seconds=.1)
        request = ModelRequest(messages=[{'role':'user','content':'返回 JSON'}],max_output_tokens=64)
        assert (await adapter.invoke(connection,request)).usage.output_tokens == 16
        mode = 'legacy'; connection.output_token_parameter='max_tokens'; connection.json_mode=False
        assert (await adapter.invoke(connection,request)).output == {'text':'替身'}
        connection.output_token_parameter='max_completion_tokens'; connection.json_mode=True
        mode = 'missing'
        assert (await adapter.invoke(connection,request)).usage.quality == 'unsupported'
        for mode in ('bad-usage','bad-total','truncated','refused','bad-json','nan','http','timeout'):
            try: await adapter.invoke(connection,request)
            except PlatformError as exc:
                expected = {'http':'MODEL_TRANSPORT_ERROR','timeout':'MODEL_TIMEOUT'}.get(mode,'OUTPUT_VALIDATION_ERROR')
                assert exc.error.code == expected, exc.error
                assert 'secret upstream' not in exc.error.model_dump_json()
                if mode in ('truncated','refused','bad-json','nan'): assert exc.usage.output_tokens == 16
            else: raise AssertionError(mode)
        mode = 'close'; started.clear(); disconnected.clear(); connection.timeout_seconds=10
        pending = asyncio.create_task(adapter.invoke(connection,request))
        await asyncio.wait_for(started.wait(),2)
        await asyncio.wait_for(adapter.close(),2)
        await asyncio.wait_for(disconnected.wait(),2)
        assert pending.exception().error.code == 'MODEL_TRANSPORT_ERROR'
        assert len(calls) == 12
    for mode in ('success','strict','missing','truncated'):
        calls.clear()
        async def graph_response(head,body,reader):
            assert head.startswith(b'POST /v1/chat/completions ')
            calls.append(json.loads(body))
            data = completion(qualitative(2))
            if mode == 'missing': data.pop('usage')
            if mode == 'truncated': data['choices'][0]['finish_reason'] = 'length'
            return 200,data
        async with local_http(graph_response) as url:
            app, service = configure(url+'/v1', ROOT/'instance',strict=(mode=='strict'),adapter='openai-chat')
            run = await execute(app,service,{'targetText':'甲乙\n丙丁','comparisonTexts':['甲乙','无关']})
            if mode == 'success':
                assert run.status == 'completed', run.error
                assert run.result['quantitative']['items'][0]['similarity'] == .5
                assert len(run.result['qualitative']['items']) == 2
                assert run.usage['tokens']['global']['totalTokens'] == 48
            else:
                assert run.status == 'failed' and run.result is None
                assert run.error.code == ('OUTPUT_VALIDATION_ERROR' if mode == 'truncated' else 'TOKEN_ACCOUNTING_UNSUPPORTED')
            assert run.usage['loops']['global'] == 1
            assert len(calls) == (0 if mode == 'strict' else 1)
    print('OpenAI 兼容 API：路径/认证/参数/计量/错误/退出清理及完整查重双报告通过；全部为本地替身')


if __name__ == '__main__':
    asyncio.run(main())
