import asyncio
import httpx
from agent_platform.application import create_app
from agent_platform.contracts import StrictModel
from agent_platform.contracts.errors import upstream_error, ErrorResponse

class Item(StrictModel):
    count: int
class Input(StrictModel):
    items: list[Item]

async def main():
    app = create_app()
    @app.post('/check')
    def check(value: Input):
        return value
    @app.get('/upstream')
    def upstream():
        try:
            raise RuntimeError('Authorization: Bearer secret-test-value')
        except RuntimeError:
            raise upstream_error('model') from None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        r = await client.post('/check', json={'items': [{'count': 'secret-test-value'}]})
        assert r.status_code == 422
        assert r.json()['fieldPath'] == ['body', 'items', 0, 'count']
        assert 'secret-test-value' not in r.text
        r = await client.get('/upstream')
        assert r.status_code == 502 and r.json()['code'] == 'MODEL_TRANSPORT_ERROR'
        assert 'secret-test-value' not in r.text and 'Authorization' not in r.text
        ErrorResponse.model_validate(r.json())
    print('T04 PASS: nested HTTP field path and upstream credential exclusion')

asyncio.run(main())
