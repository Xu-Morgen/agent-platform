"""通过现有平台 API 加载资源、静态校验并保存服务；不会提交文档或调用模型。"""
import argparse
import json
import time
from pathlib import Path
import httpx


def assemble(reader, package, environment_id, connection_id):
    return {
        'name': '文档出题',
        'inputContract': reader['inputContract'],
        'outputContract': package['outputContract'],
        'flow': [
            {'kind': 'block', 'nodeId': 'read_document', 'artifactRef': reader['resourceId']},
            {'kind': 'package', 'nodeId': 'generate_questions', 'artifactRef': package['resourceId']},
        ],
        'nodeConfigurations': {
            'generate_questions': {
                'model': {'environmentId': environment_id, 'connectionId': connection_id},
                'maxOutputTokens': 4096,
                'budget': {'loopLimit': 3, 'tokenLimit': 131072},
            },
        },
        'budget': {'loopLimit': 3, 'tokenLimit': 131072},
        'retryLimit': 2,
    }


def setup(base_url, environment_id, connection_id):
    root = Path(__file__).resolve().parent
    with httpx.Client(base_url=base_url.rstrip('/'), timeout=30, trust_env=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, '/api/v1' + path, **kwargs)
            response.raise_for_status()
            return response.json()
        # 校验用户选择，避免准备完成后才发现模型连接标识错误。
        environments = request('GET', '/environments')
        if not any(env['environmentId'] == environment_id and any(
                connection['connectionId'] == connection_id and connection['kind'] == 'model'
                for connection in env['connections']) for env in environments):
            raise ValueError('所选模型连接不存在，请先在环境页面配置')
        def load(kind, path):
            job = request('POST', '/preparations', json={'kind': kind, 'path': str(path)})
            try:
                deadline = time.monotonic() + 660
                phase = None
                while job['phase'] not in ('ready', 'failed', 'cancelled'):
                    if phase != job['phase']:
                        phase = job['phase']
                        print(f'{kind}: {phase}', flush=True)
                    if time.monotonic() > deadline:
                        raise TimeoutError('资源准备超时')
                    time.sleep(.5)
                    job = request('GET', '/preparations/' + job['jobId'])
                if job['phase'] != 'ready':
                    raise RuntimeError(json.dumps(job['error'], ensure_ascii=False))
                return job['resource']
            except BaseException:
                request('POST', '/preparations/' + job['jobId'] + '/cancel')
                raise
        reader = load('block', root / 'read_document.py')
        package = load('package', root / 'document-question-generator')
        draft = assemble(reader, package, environment_id, connection_id)
        validation = request('POST', '/flows/validate', json=draft)
        if not validation['valid']:
            raise RuntimeError(json.dumps(validation, ensure_ascii=False))
        service = request('POST', '/services', json={'name': draft['name'], 'flow': draft})
        print(json.dumps(service, ensure_ascii=False, indent=2))
        return service


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True, help='当前本地平台后端地址')
    parser.add_argument('--environment-id', required=True)
    parser.add_argument('--connection-id', required=True)
    args = parser.parse_args()
    setup(args.base_url, args.environment_id, args.connection_id)
