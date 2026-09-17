"""解析示例产品内的资源占位符；只加载模块并创建草稿，不生成实例或调用模型。"""
import argparse
import json
from pathlib import Path
import httpx


def load_template(request, root, name, environment_id=None, strict=True):
    root = Path(root).resolve()
    recipe = json.loads((root / 'flows' / (name + '.json')).read_text())
    resources = {}
    for key, value in recipe['resources'].items():
        resources[key] = request('POST', 'catalog/load', json={**value, 'path': str(root / value['path'])})
    values = {'environmentId': environment_id, 'strictTokenLimit': strict}
    for name, resource in resources.items():
        for key, value in resource.items():
            values[name + '.' + key] = value
    def resolve(value):
        if isinstance(value, dict): return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list): return [resolve(v) for v in value]
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            key = value[2:-1]
            if values.get(key) is None: raise ValueError('模板需要配置：' + key)
            return values[key]
        return value
    return resolve(recipe['flow'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('flow')
    parser.add_argument('--platform-url', default='http://127.0.0.1:8000')
    parser.add_argument('--environment-id')
    parser.add_argument('--non-strict', action='store_true')
    args = parser.parse_args()
    with httpx.Client(base_url=args.platform_url, timeout=30, trust_env=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, '/api/v1/' + path, **kwargs)
            response.raise_for_status()
            return response.json()
        flow = load_template(request, args.root, args.flow, args.environment_id, not args.non_strict)
        draft = request('POST', 'drafts', json={'content': flow})
        print('已创建会话草稿：' + draft['draftId'] + '；在服务页刷新后选择草稿，检查配置并保存实例。')


if __name__ == '__main__':
    main()
