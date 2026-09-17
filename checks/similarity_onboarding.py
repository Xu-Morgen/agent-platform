"""从干净后端进程按 samples/README.md 运行 HTTP 接入脚本。"""
import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import httpx
from local_http import local_http
from similarity_support import qualitative, ollama_response


async def backend():
    read_fd, write_fd = os.pipe()
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'agent_platform',
        '--port','0','--control-fd',str(write_fd), pass_fds=(write_fd,),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    os.close(write_fd)
    def ready():
        with os.fdopen(read_fd) as channel:
            return json.loads(channel.readline())['address']
    address = await asyncio.wait_for(asyncio.to_thread(ready), 10)
    return process, address


async def stop(process):
    process.stdin.write(b'{"protocolVersion":1,"type":"shutdown"}\n')
    await process.stdin.drain()
    await asyncio.wait_for(process.wait(), 10)
    assert process.returncode == 0


async def main(adapter='ollama-chat'):
    calls = []
    async def respond(head, body, reader):
        calls.append(json.loads(body))
        if adapter == 'openai-chat':
            from openai_chat import completion
            assert head.startswith(b'POST /v1/chat/completions ')
            return 200, completion(qualitative(2))
        return 200, ollama_response(qualitative(2))
    async with local_http(respond) as url:
        process, address = await backend()
        try:
            with TemporaryDirectory() as directory:
                output = Path(directory) / 'report.json'
                client = await asyncio.create_subprocess_exec(sys.executable, 'samples/invoke_similarity.py',
                    '--adapter',adapter,'--platform-url',address,'--model-url',url + ('/v1' if adapter == 'openai-chat' else ''),'--model','local-http-synthetic',
                    '--non-strict','--output',str(output), stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await asyncio.wait_for(client.communicate(), 20)
                assert client.returncode == 0, stderr.decode() + stdout.decode()
                record = json.loads(output.read_text())
                assert record['adapter'] == adapter
                assert record['status'] == 'completed' and record['usage']['loops']['global'] == 1
                assert set(record['result']) == {'quantitative','qualitative'}
                assert len(calls) == 1
                assert 'environmentSnapshot' not in record and 'input' not in record
        finally:
            await stop(process)
        restarted, address = await backend()
        try:
            async with httpx.AsyncClient(base_url=address, trust_env=False) as client:
                assert (await client.get('/api/v1/runs/' + record['runId'])).status_code == 404
                assert (await client.get('/api/v1/services')).json() == []
        finally:
            await stop(restarted)
    print('I8-T07：新版拼图，干净后端→创建环境→加载→保存→提交→查询双报告→退出；重启旧 runId=404、服务清空')


if __name__ == '__main__':
    asyncio.run(main())
    asyncio.run(main('openai-chat'))
