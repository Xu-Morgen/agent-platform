import asyncio
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import httpx
from agent_platform.application import create_app

async def main():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for request in [
            {'kind': 'package', 'path': 'examples/configuration/package'},
            {'kind': 'block', 'path': 'examples/flows/blocks/rename.py'},
            {'kind': 'contract', 'path': 'examples/flows/blocks/rename.py', 'symbol': 'Output'},
        ]:
            response = await client.post('/api/v1/catalog/load', json=request)
            assert response.status_code == 200, response.text
            value = response.json()
            assert value['resourceId'] and value['schemas'] and value['digest']
            assert (await client.get('/api/v1/catalog/' + value['resourceId'])).json() == value
            if request['kind'] == 'package':
                assert value['configurationContract']
        listing = (await client.get('/api/v1/catalog')).json()
        assert len(listing) == 3 and not app.state.environments.list()
        assert 'credential' not in str(listing).lower()
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.py'
            path.write_text('import nonexistent_example_dependency')
            response = await client.post('/api/v1/catalog/load', json={'kind': 'block', 'path': str(path)})
            assert response.status_code == 422 and 'nonexistent_example_dependency' in response.text
            package = Path(directory) / 'package'
            shutil.copytree('examples/configuration/package', package)
            manifest_path = package / 'package.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['runtimeRequirements']['dependencies'].append('nonexistent-example-distribution>=1')
            manifest_path.write_text(json.dumps(manifest))
            response = await client.post('/api/v1/catalog/load', json={'kind': 'package', 'path': str(package)})
            assert response.status_code == 422 and 'nonexistent-example-distribution' in response.text
            assert response.json()['fieldPath'][-1] == 1
    print('catalog: OK (无环境加载、资源查询、契约、缺失依赖、无凭据)')

asyncio.run(main())
