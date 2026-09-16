import asyncio
import httpx
from agent_platform.application import create_app

async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
        body = {'name': '合成环境', 'connections': [{'connectionId': 'model', 'kind': 'model', 'baseUrl': 'http://localhost:9000', 'model': 'synthetic', 'credential': 'synthetic-secret'}]}
        response = await client.post('/api/v1/environments', json=body)
        assert response.status_code == 201, response.text
        saved = response.json()
        assert 'synthetic-secret' not in response.text and saved['revision'] == 1
        body['connections'][0].pop('credential')
        body['connections'][0]['credentialRef'] = saved['connections'][0]['credentialRef']
        response = await client.put('/api/v1/environments/' + saved['environmentId'], json=body)
        assert response.json()['revision'] == 2
        body['connections'][0]['baseUrl'] = 'https://user:synthetic-secret@example.test'
        response = await client.put('/api/v1/environments/' + saved['environmentId'], json=body)
        assert response.status_code == 422 and response.json()['fieldPath'][-1] == 'baseUrl'
        assert 'synthetic-secret' not in response.text
        assert (await client.get('/api/v1/environments')).json()[0]['revision'] == 2
    print('I2-T02 PASS: create/update, credential references, field errors, unchanged on failure')

asyncio.run(main())
