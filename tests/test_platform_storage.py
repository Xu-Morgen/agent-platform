"""轻量边界验证：不连接外部模型，不替代 PostgreSQL/真实模型验收。"""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
import httpx

from agent_platform.application import create_app
from agent_platform.storage import MemoryStore, storage_error
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.runs import RunSubmit, StepRecord
from agent_platform.contracts.errors import PlatformError


class RefusingStore(MemoryStore):
    reject = False

    def write(self, documents):
        if self.reject:
            raise storage_error('验证用写入失败')
        super().write(documents)


def reopened(store):
    """JSON 往返后使用全新仓储对象；不复用旧实例、模块或图对象。"""
    other = MemoryStore()
    other._documents = json.loads(json.dumps(store._documents))
    return create_app(other)


def pure_service(app, path):
    resource = app.state.catalog.load(CatalogLoad(kind='block', path=str(path)))
    flow = FlowDraft.model_validate({
        'name': 'pure', 'inputContract': resource.input_contract,
        'outputContract': resource.output_contract,
        'flow': [{'nodeId': 'calculate', 'kind': 'block', 'artifactRef': resource.resource_id,
                  'inputs': [{'source': {'kind': 'input'}}]}],
        'output': [{'source': {'kind': 'node', 'nodeId': 'calculate'}}],
    })
    return app.state.services.save(ServiceWrite(name='pure', flow=flow))


class PersistenceChecks(unittest.IsolatedAsyncioTestCase):
    async def test_deleted_source_restart_execution_and_rollback(self):
        store = MemoryStore()
        app = create_app(store)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'block.py'
            path.write_text("from agent_platform.blocks import block\n@block(id='sum-test',version='1.0.0',name='test')\ndef compute(value: int) -> int:\n    return value + 1\n")
            first = pure_service(app, path)
        flow = app.state.services.resolve_current(first.service_id).draft
        second = app.state.services.save(ServiceWrite(name='renamed', flow=flow), first.service_id)
        activated = app.state.services.activate(first.service_id, first.active_instance_id)
        restored = reopened(store)
        self.assertEqual(restored.state.services.get(first.service_id), activated)
        self.assertEqual(len(restored.state.services.history(first.service_id)), 2)
        third = restored.state.services.save(ServiceWrite(name='third', flow=flow), first.service_id)
        self.assertEqual(third.current.revision, second.current.revision + 1)
        self.assertEqual(third.current.version, '1.2')
        async with restored.router.lifespan_context(restored):
            run = restored.state.submission.submit(RunSubmit(service_id=first.service_id, input=41))
            await asyncio.wait_for(restored.state.submission.queue.join(), 3)
            final = restored.state.runs.get(run.run_id)
            self.assertEqual(final.status, 'completed')
            self.assertEqual(final.result, 42)
        again = reopened(restored.state.store)
        self.assertEqual(again.state.runs.get(run.run_id).result, 42)

    async def test_interrupted_runs_and_environment_release(self):
        store = MemoryStore()
        app = create_app(store)
        env = app.state.environments.save(EnvironmentWrite(name='api', connections=[{
            'kind': 'api', 'connectionId': 'api', 'baseUrl': 'http://127.0.0.1:1'}]))
        queued = app.state.runs.create(service_id='s', instance_id='i', version='1.0', revision=1, input={})
        running = app.state.runs.create(service_id='s', instance_id='i', version='1.0', revision=1, input={})
        app.state.runs.update(running.run_id, status='running', cancel_requested=True, cancel_phase='waiting_transport',
            steps=[StepRecord(run_id=running.run_id, step_id='external')])
        app.state.environments.occupy([env.environment_id], running.run_id)
        restored = reopened(store)
        for run in (queued, running):
            value = restored.state.runs.get(run.run_id)
            self.assertEqual(value.status, 'failed')
            self.assertEqual(value.error.code, 'APPLICATION_INTERRUPTED')
            self.assertIsNone(value.cancel_phase)
        self.assertEqual(restored.state.runs.get(running.run_id).steps[0].status, 'failed')
        self.assertFalse(restored.state.environments.get(env.environment_id).active_run_ids)
        self.assertTrue(restored.state.submission.queue.empty())
        self.assertEqual(reopened(restored.state.store).state.runs.get(running.run_id), restored.state.runs.get(running.run_id))

    async def test_failed_publish_does_not_move_pointer_or_consume_revision(self):
        store = RefusingStore()
        app = create_app(store)
        first = pure_service(app, 'samples/blocks/minimal.py')
        request = ServiceWrite(name='new', flow=app.state.services.resolve_current(first.service_id).draft)
        store.reject = True
        with self.assertRaises(PlatformError):
            app.state.services.save(request, first.service_id)
        self.assertEqual(app.state.services.get(first.service_id), first)
        self.assertEqual(len(app.state.services.history(first.service_id)), 1)
        store.reject = False
        second = app.state.services.save(request, first.service_id)
        self.assertEqual(second.current.revision, 2)
        store.reject = True
        with self.assertRaises(PlatformError):
            app.state.services.activate(first.service_id, first.active_instance_id)
        self.assertEqual(app.state.services.get(first.service_id), second)

    async def test_corrupt_resource_refuses_restore(self):
        store = MemoryStore()
        app = create_app(store)
        pure_service(app, 'samples/blocks/minimal.py')
        document = next(iter(store._documents['resources'].values()))
        document['files']['block.py'] = 'YQ=='
        with self.assertRaisesRegex(ValueError, '摘要'):
            reopened(store)

    async def test_task_listing_and_draft_http(self):
        app = create_app(MemoryStore())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            info = await client.get('/api/v1/platform')
            self.assertFalse(info.json()['persistent'])
            response = await client.post('/api/v1/drafts', json={'content': {'name': '保存中的草稿'}})
            self.assertEqual(response.status_code, 201, response.text)
            restored = reopened(app.state.store)
            self.assertEqual(len(restored.state.drafts.list()), 1)
            for service in ['a', 'b', 'a']:
                app.state.runs.create(service_id=service, instance_id='i', version='1.0', revision=1, input={})
            page = await client.get('/api/v1/runs?serviceId=a&status=queued&limit=1&offset=1')
            self.assertEqual(len(page.json()), 1)
            self.assertEqual(page.json()[0]['serviceId'], 'a')
            self.assertEqual((await client.get('/api/v1/runs?limit=201')).status_code, 422)


if __name__ == '__main__':
    unittest.main()
