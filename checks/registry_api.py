import asyncio
import httpx
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
from agent_platform.application import create_app

async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
        for kind, name in [('block','block'), ('package','package'), ('package','second'), ('instance','instance')]:
            response = await client.post('/api/v1/registry/load', json={'kind':kind,'path':'examples/configuration/'+name})
            assert response.status_code == 200, response.text
            assert response.json()['id'] and response.json()['schemas']
        loaded = response.json()
        assert loaded['definition']['budget']['loopLimit'] == 4
        response = await client.post('/api/v1/services', json={'name':'加载样例','definitionLoadId':loaded['loadId'],'definition':loaded['definition']})
        assert response.status_code == 201, response.text
        for directory in ['missing-synthetic-secret-directory']:
            response = await client.post('/api/v1/registry/load', json={'kind':'package','path':directory})
            assert response.status_code == 422 and response.json()['fieldPath'] == ['path']
            assert directory not in response.text
        for kind, directory, message in [
            ('instance', 'samples/assignment-similarity/instance/instance.json', '文件夹'),
            ('instance', 'samples/assignment-similarity', 'instance.json'),
            ('package', 'samples/assignment-similarity/instance', 'package.json'),
        ]:
            response = await client.post('/api/v1/registry/load', json={'kind': kind, 'path': directory})
            assert response.status_code == 422 and response.json()['fieldPath'] == ['path']
            assert message in response.json()['message']
        with TemporaryDirectory() as directory:
            shutil.copytree('examples/configuration/block', directory, dirs_exist_ok=True)
            Path(directory, 'block.py').write_text('')
            response = await client.post('/api/v1/registry/load', json={'kind':'block','path':directory})
            assert response.status_code == 422 and response.json()['fieldPath'] == ['entry']
    print('I2-T12 PASS: package/block/instance handles and schemas, invalid paths/entries, no raw exception leaks')

asyncio.run(main())
