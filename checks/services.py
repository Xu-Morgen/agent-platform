import asyncio
import httpx
from agent_platform.application import create_app

def setup_app():
    app = create_app()
    for name in ('package', 'second'):
        app.state.packages.load('examples/configuration/' + name)
    app.state.blocks.load('examples/configuration/block')
    loaded = app.state.definitions.load('examples/configuration/instance')
    body = {'name':'合成服务','definitionLoadId':loaded.load_id,'definition':loaded.definition.model_dump(mode='json', by_alias=True, exclude_unset=True)}
    return app, body

async def main():
    app, body = setup_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/services', json=body)
        assert response.status_code == 201, response.text
        a = response.json()
        key = a['serviceId']
        assert a['current']['version'] == '1.0'
        body['definition']['configRefs'][0]['values']['loopLimit'] = 3
        response = await client.post(f'/api/v1/services/{key}/versions', json=body)
        assert response.status_code == 201, response.text
        b = response.json()
        assert b['serviceId'] == key and b['activeInstanceId'] != a['activeInstanceId']
        assert b['current']['version'] == '1.1'
        body['definition']['entry'] = 'missing:run'
        response = await client.post(f'/api/v1/services/{key}/versions', json=body)
        assert response.status_code == 422
        schema = (await client.get(f'/api/v1/services/{key}/schema')).json()
        assert schema['service'] == b and schema['input']['required'] == ['text']
        assert 'loopLimit' in schema['configurationSchemas']['packages.echo']['properties']
        assert (await client.get('/api/v1/services/missing/schema')).status_code == 404
        assert len(app.state.services._history[key]) == 2
        assert (await client.get('/api/v1/services')).json() == [b]
    print('I2-T08 PASS: stable service ID, current schema, atomic failure, new immutable instance')

if __name__ == '__main__': asyncio.run(main())
