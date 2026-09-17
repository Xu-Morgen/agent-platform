import asyncio
import httpx
from flow_execution import fixture, bind, ref
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.errors import PlatformError

async def main():
    app, draft, _ = fixture()
    doc = draft.model_dump(by_alias=True)
    doc['flow'] = doc['flow'][:1]
    doc.update(outputContract=app.state.catalog.get(doc['flow'][0]['artifactRef']).output_contract,
        output=bind(ref('convert')), nodeConfigurations={}, budget=None, examples=[{'name': '有效样例', 'input': {'legacyText': '示例'}}])
    write = ServiceWrite(name='纯块实例', flow=FlowDraft.model_validate(doc))
    manager = app.state.services
    saved = manager.save(write)
    snapshot = manager.resolve_current(saved.service_id)
    assert await snapshot.graph.run({'legacyText': '源快照'}) == {'text': '源快照'}
    # 清空当前目录注册表不改变实例引用的契约与模块。
    app.state.catalog._artifacts.clear()
    assert await snapshot.graph.run({'legacyText': '仍可执行'}) == {'text': '仍可执行'}
    schema = manager.schema(saved.service_id)
    assert schema.examples[0]['input'] == {'legacyText': '示例'} and schema.compiler_version
    bad = write.model_copy(deep=True)
    bad.flow.flow[0].inputs = []
    count = len(manager.snapshots._items)
    try: manager.save(bad, saved.service_id)
    except PlatformError: pass
    else: raise AssertionError('非法实例已保存')
    assert len(manager.snapshots._items) == count and manager.get(saved.service_id) == saved
    app, draft, _ = fixture()
    draft.node_configurations = {}
    try: app.state.services.save(ServiceWrite(name='缺失包配置', flow=draft))
    except PlatformError: pass
    else: raise AssertionError()
    assert not app.state.services.list()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/services', json=write.model_dump(mode='json', by_alias=True))
        # 模块 id 是内容寻址，同内容新会话重新加载可解析。
        assert response.status_code == 201, response.text
        schema = await client.get('/api/v1/services/' + response.json()['serviceId'] + '/schema')
        assert schema.status_code == 200 and schema.json()['flow']['examples']
    print('flow snapshots: OK (纯块保存、Schema 样例、固定资源、非法保存原子拒绝、HTTP 新协议)')

asyncio.run(main())
