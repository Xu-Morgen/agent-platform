"""只调用既有 HTTP 接口的接入样例；后端须与本脚本共享本地文件系统。"""
import argparse
import json
import os
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import time
import httpx

ROOT = Path(__file__).resolve().parent / 'assignment-similarity'


def invoke(args):
    connection = {'connectionId':'model', 'kind':'model', 'baseUrl':args.model_url,
                  'model':args.model, 'timeoutSeconds':args.timeout, 'modelAdapter':args.adapter,
                  'outputTokenParameter':args.output_token_parameter, 'jsonMode':not args.no_json_mode}
    if args.credential_env:
        connection['credential'] = os.environ[args.credential_env]
    with httpx.Client(base_url=args.platform_url, timeout=30.0, trust_env=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, '/api/v1/' + path, **kwargs)
            if response.is_error:
                # 不输出请求体、模型地址或凭据。
                error = response.json()
                raise RuntimeError(f"HTTP {response.status_code}: {error.get('code')} {error.get('stage')} {error.get('fieldPath')}")
            return response.json()
        request('GET', 'health')
        environment = request('POST', 'environments', json={'name':'查重样例环境','connections':[connection]})
        request('POST', 'registry/load', json={'kind':'package','path':str(ROOT / 'packages/semantic')})
        # 加载实例 API 已校验环境引用，故先在临时副本内替换占位符。
        with TemporaryDirectory(prefix='similarity-instance-') as directory:
            instance = Path(directory) / 'instance'
            copytree(ROOT / 'instance', instance)
            path = instance / 'instance.json'
            definition = json.loads(path.read_text())
            definition['environmentRefs'] = [environment['environmentId']]
            definition['budget']['strictTokenLimit'] = not args.non_strict
            for binding in definition['capabilityBindings']:
                binding['environmentId'] = environment['environmentId']
            path.write_text(json.dumps(definition, ensure_ascii=False))
            loaded = request('POST', 'registry/load', json={'kind':'instance','path':str(instance)})
            service = request('POST', 'services', json={'name':'文本查重',
                'definitionLoadId':loaded['loadId'], 'definition':loaded['definition']})
        value = json.loads(Path(args.input).read_text())
        run = request('POST', 'runs', json={'serviceId':service['serviceId'],'input':value})
        deadline = time.monotonic() + args.timeout + 30
        while run['status'] not in ('completed','failed','cancelled'):
            if time.monotonic() > deadline:
                raise TimeoutError('等待任务终态超时，请按 runId 查询或取消：' + run['runId'])
            time.sleep(.2)
            run = request('GET', 'runs/' + run['runId'])
        result = request('GET', 'runs/' + run['runId'] + '/result')['result'] if run['status'] == 'completed' else None
        # 只导出业务结果、状态及计量，不导出原输入、环境地址或凭据引用。
        record = {'status':run['status'], 'runId':run['runId'], 'serviceId':service['serviceId'],
                  'model':args.model, 'adapter':args.adapter, 'strictTokenLimit':not args.non_strict,
                  'usage':run['usage'], 'result':result, 'error':run['error']}
        if args.output:
            Path(args.output).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return run['status'] == 'completed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform-url', default='http://127.0.0.1:8000')
    parser.add_argument('--adapter', choices=['openai-chat', 'ollama-chat'], default='openai-chat')
    parser.add_argument('--output-token-parameter', choices=['max_completion_tokens','max_tokens'], default='max_completion_tokens')
    parser.add_argument('--no-json-mode', action='store_true', help='兼容不支持 response_format 的端点；仍严格解析 JSON')
    parser.add_argument('--model-url', required=True, help='OpenAI 兼容 API 根路径（通常以 /v1 结尾）；Ollama 则填服务根地址')
    parser.add_argument('--model', required=True)
    parser.add_argument('--credential-env', help='可选：存放模型凭据的环境变量名称')
    parser.add_argument('--non-strict', action='store_true', help='显式使用非严格 token 模式；当前两种适配器均需选择')
    parser.add_argument('--input', default=str(ROOT / 'examples/input.json'))
    parser.add_argument('--output', help='可选：将脱敏结果写入指定路径')
    parser.add_argument('--timeout', type=float, default=180.0)
    raise SystemExit(0 if invoke(parser.parse_args()) else 1)


if __name__ == '__main__':
    main()
