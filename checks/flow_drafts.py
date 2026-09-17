import asyncio
from copy import deepcopy
import httpx
from agent_platform.application import create_app
from flow_ports import fixture, bind, ref

async def main():
    app = create_app()
    app.state.catalog, draft = fixture()
    # while 的条件块单独作用域，循环初始/反馈与最终输出完整。
    draft['flow'].append({'nodeId': 'while', 'kind': 'while', 'maxIterations': 3,
        'condition': {'nodeId': 'loopCondition', 'kind': 'block', 'artifactRef': draft['flow'][1]['artifactRef'],
                      'inputs': bind({'kind': 'carry', 'nodeId': 'while'})}, 'body': [],
        'carry': {'contract': draft['outputContract'], 'initial': bind(ref('repeat')),
                  'update': bind({'kind': 'carry', 'nodeId': 'while'})}})
    draft['output'] = bind(ref('while'))
    draft['examples'] = [{'name': '正常输入', 'input': {'legacyText': 'synthetic'}}]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/drafts', json={'content': {'name': '未完成', 'flow': [{'kind': 'while'}]}})
        assert response.status_code == 201, response.text
        document = response.json(); draft_id = document['draftId']
        assert 'instanceId' not in document and 'instanceId' not in document['content']
        assert not (await client.get('/api/v1/services')).json()
        assert not (await client.post(f'/api/v1/drafts/{draft_id}/validate')).json()['valid']
        response = await client.put(f'/api/v1/drafts/{draft_id}', json={'content': draft})
        assert response.status_code == 200, response.text
        result = (await client.post(f'/api/v1/drafts/{draft_id}/validate')).json()
        assert result['valid'], result
        fetched = (await client.get(f'/api/v1/drafts/{draft_id}')).json()
        assert fetched['content']['flow'] == draft['flow']
        invalid = deepcopy(draft)
        invalid['examples'][0]['input']['legacyText'] = 123
        result = (await client.post('/api/v1/flows/validate', json={'content': invalid})).json()
        assert not result['valid'] and any('字符串' in i['reason'] and i['fieldPath'] == ['examples', 0, 'input', 'legacyText'] for i in result['issues'])
        assert not app.state.services.list()
        assert len((await client.get('/api/v1/drafts')).json()) == 1
        package = (await client.post('/api/v1/catalog/load', json={'kind': 'package', 'path': 'examples/execution/model-package'})).json()
        environment = (await client.post('/api/v1/environments', json={'name': '合成模型环境', 'connections': [
            {'connectionId': 'model', 'kind': 'model', 'baseUrl': 'http://localhost:11434', 'model': 'synthetic'},
            {'connectionId': 'api', 'kind': 'api', 'baseUrl': 'http://localhost:8080'}]})).json()
        model_draft = {'name': '业务包预检', 'inputContract': package['inputContract'], 'outputContract': package['outputContract'],
            'flow': [{'nodeId': 'model', 'kind': 'package', 'artifactRef': package['resourceId'], 'inputs': bind({'kind': 'input'})}],
            'output': bind(ref('model')), 'budget': {'loopLimit': 1, 'tokenLimit': 1024, 'strictTokenLimit': False},
            'nodeConfigurations': {'model': {'parameters': {'maxOutputTokens': 64}, 'budget': {'loopLimit': 1, 'tokenLimit': 1024},
                'capabilities': {'chat': {'kind': 'model', 'environmentId': environment['environmentId'], 'connectionId': 'model'}}}}}
        result = (await client.post('/api/v1/flows/validate', json={'content': model_draft})).json()
        assert result['valid'], result
        model_draft['nodeConfigurations']['model']['capabilities']['chat']['connectionId'] = 'api'
        result = (await client.post('/api/v1/flows/validate', json={'content': model_draft})).json()
        assert not result['valid'] and any('连接类型' in issue['reason'] and issue['nodeId'] == 'model' for issue in result['issues'])
        assert not app.state.services.list()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
        assert (await client.get(f'/api/v1/drafts/{draft_id}')).status_code == 404
    print('flow drafts: OK (未完成保存、顺序/分支/repeat/while 纯块/业务包预检、错误连接类型、样例定位、不可调用与重启清空)')

asyncio.run(main())
