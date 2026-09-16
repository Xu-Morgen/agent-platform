import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import httpx
from services import setup_app

async def main():
    app, body = setup_app()
    with TemporaryDirectory() as directory:
        shutil.copytree('examples/configuration/package', directory, dirs_exist_ok=True)
        manifest = json.loads(Path(directory, 'package.json').read_text())
        manifest['version'] = '2.0.0'
        manifest['requiredCapabilities'][0]['kind'] = 'api'
        Path(directory, 'package.json').write_text(json.dumps(manifest))
        app.state.packages.load(directory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        environment = {'name':'当前环境','connections':[{'connectionId':'api','kind':'api','baseUrl':'https://original.example.test'}]}
        response = await client.post('/api/v1/environments', json=environment)
        env_id = response.json()['environmentId']
        body['definition']['environmentRefs'] = [env_id]
        body['definition']['packageBindings'][0]['version'] = '2.0.0'
        body['definition']['capabilityBindings'][0] = {'packageBindingId':'echo','capabilityId':'identity','kind':'api','environmentId':env_id,'connectionId':'api','inputModel':'models:Message','outputModel':'models:Message'}
        response = await client.post('/api/v1/services', json=body)
        assert response.status_code == 201, response.text
        a = response.json()
        key = a['serviceId']
        body['definition']['configRefs'][0]['values']['prefix'] = 'B'
        b = (await client.post(f'/api/v1/services/{key}/versions', json=body)).json()
        environment['connections'][0]['baseUrl'] = 'https://current.example.test'
        await client.put('/api/v1/environments/' + env_id, json=environment)
        response = await client.post(f'/api/v1/services/{key}/activate', json={'instanceId':a['activeInstanceId']})
        assert response.json() == a, response.text
        assert app.state.environments.get(env_id).connections[0].base_url == 'https://current.example.test'
        await client.post(f'/api/v1/services/{key}/activate', json={'instanceId':b['activeInstanceId']})
        environment['connections'][0].update(kind='model', model='synthetic')
        await client.put('/api/v1/environments/' + env_id, json=environment)
        response = await client.post(f'/api/v1/services/{key}/activate', json={'instanceId':a['activeInstanceId']})
        assert response.status_code == 422 and response.json()['fieldPath'][-1] == 'connectionId'
        assert app.state.services.get(key).active_instance_id == b['activeInstanceId']
        assert len((await client.get(f'/api/v1/services/{key}/versions')).json()) == 2
    print('I2-T10 PASS: original A reactivated, current URL retained, incompatible environment preserves B, no new version')

asyncio.run(main())
