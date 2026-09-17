import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import httpx
from flow_execution import fixture
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.errors import PlatformError

async def main():
    app, draft, env = fixture()
    manager = app.state.services
    first = manager.save(ServiceWrite(name='版本', flow=draft))
    key = first.service_id
    draft.node_configurations['generate'].parameters['maxOutputTokens'] = 32
    minor = manager.save(ServiceWrite(name='版本', flow=draft), key)
    assert minor.current.version == '1.1' and minor.current.change_kind == 'minor'
    draft.flow[0].inputs[0].source.path = []
    draft.examples = []
    # 实际块源文件改动后重新加载，旧快照仍执行原字节。
    old_ref = draft.flow[0].artifact_ref
    original = Path('examples/flows/blocks/rename.py').read_text()
    with TemporaryDirectory() as folder:
        path = Path(folder) / 'rename.py'
        path.write_text(original.replace('1.0.0', '2.0.0').replace('value.legacy_text', 'value.legacy_text + "新版"'))
        module = app.state.catalog.load(CatalogLoad(kind='block', path=str(path)))
        draft.flow[0].artifact_ref = module.resource_id
        major = manager.save(ServiceWrite(name='版本', flow=draft), key)
        assert major.current.version == '2.0' and major.current.change_kind == 'major'
        path.write_text('源码已删除或改坏')
        assert (await manager.resolve_current(key).catalog.artifact(module.resource_id).invoke({'legacyText': '测试'})).text == '测试新版'
    draft.flow[0].artifact_ref = old_ref
    draft.node_configurations['generate'].parameters['maxOutputTokens'] = 16
    breaking = manager.save(ServiceWrite(name='版本', flow=draft), key)
    assert breaking.current.version == '3.0' and breaking.current.change_kind == 'breaking'
    app.state.environments.save(EnvironmentWrite(name='当前环境', connections=[{
        'connectionId': 'model', 'kind': 'model', 'baseUrl': 'http://localhost:11434', 'model': 'changed'}]), env.environment_id)
    assert manager.get(key).current.version == '3.0'
    restored = manager.activate(key, first.active_instance_id)
    assert restored.active_instance_id == first.active_instance_id and len(manager.history(key)) == 4
    assert app.state.environments.get(env.environment_id).connections[0].model == 'changed'
    app.state.environments.save(EnvironmentWrite(name='缺少连接', connections=[{'connectionId': 'other', 'kind': 'model', 'baseUrl': 'http://localhost:11434', 'model': 'changed'}]), env.environment_id)
    try: manager.activate(key, breaking.active_instance_id)
    except PlatformError: pass
    else: raise AssertionError()
    assert manager.get(key) == restored
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        url = f'/api/v1/services/{key}/versions/{first.active_instance_id}'
        history = await client.get(url)
        assert history.status_code == 200
        assert history.json()['flow']['nodeConfigurations']['generate']['parameters']['maxOutputTokens'] == 64
        copied = await client.post(url + '/draft')
        assert copied.status_code == 201 and copied.json()['draftId']
        copied.json()['content']['flow'].clear()
        assert manager.historical(key, first.active_instance_id).flow.flow
    app2, flow2, env2 = fixture()
    mgr = app2.state.services
    svc = mgr.save(ServiceWrite(name='分类边界', flow=flow2))
    other_env = app2.state.environments.save(EnvironmentWrite(name='另一环境', connections=[{
        'connectionId': 'model', 'kind': 'model', 'baseUrl': 'http://localhost:11434', 'model': 'other'}]))
    flow2.node_configurations['generate'].capabilities['chat'].environment_id = other_env.environment_id
    assert mgr.save(ServiceWrite(name='分类边界', flow=flow2), svc.service_id).current.change_kind == 'minor'
    # 同一块新增节点即拓扑变化；修改契约身份也是结构变化。
    duplicate = flow2.flow[0].model_copy(deep=True); duplicate.node_id = 'another'
    flow2.flow.insert(1, duplicate)
    assert mgr.save(ServiceWrite(name='分类边界', flow=flow2), svc.service_id).current.change_kind == 'major'
    catalog = app2.state.catalog
    catalog._contracts['contract:alternate'] = catalog.contract(flow2.input_contract)
    flow2.input_contract = 'contract:alternate'
    assert mgr.save(ServiceWrite(name='分类边界', flow=flow2), svc.service_id).current.change_kind == 'major'
    print('flow versions: OK (参数 minor、块内容 major、同时 breaking、源字节隔离、当前环境回退、失败不切换、历史复制)')

asyncio.run(main())
