"""真实 PostgreSQL 的小型集成检查，仅操作临时目录，不调用模型。"""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from pydantic import SecretStr
from agent_platform.application import create_app
from agent_platform.storage.local import LocalPostgres
from agent_platform.storage.postgres import PostgresStore
from agent_platform.storage import configured_store
from agent_platform.contracts.drafts import DraftWrite
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.errors import PlatformError
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.services import ServiceWrite
from test_platform_storage import pure_service


class LocalPostgresChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agent-postgres-test-')
        self.directory = Path(self.temporary.name) / 'storage'

    def tearDown(self):
        self.temporary.cleanup()

    async def test_actual_restart_source_credentials_versions_and_runs(self):
        secret = 'synthetic-test-credential'
        with LocalPostgres(self.directory) as db, db.environment():
            app = create_app()
            async with app.router.lifespan_context(app):
                env = app.state.environments.save(EnvironmentWrite(name='test', connections=[{
                    'kind': 'api', 'connectionId': 'api', 'baseUrl': 'http://127.0.0.1:1', 'credential': SecretStr(secret)}]))
                draft = app.state.drafts.save(DraftWrite(content={'name': 'saved draft'}))
                source = Path(self.temporary.name) / 'source.py'
                source.write_text("from agent_platform.blocks import block\n@block(id='durable',version='1.0.0',name='durable')\ndef calculate(value: int) -> int:\n    return value + 1\n")
                service = pure_service(app, source)
                flow = app.state.services.resolve_current(service.service_id).draft
                app.state.services.save(ServiceWrite(name='v2', flow=flow), service.service_id)
                app.state.services.activate(service.service_id, service.active_instance_id)
                source.unlink()
                completed = app.state.submission.submit(RunSubmit(service_id=service.service_id, input=41))
                await asyncio.wait_for(app.state.submission.queue.join(), 5)
                self.assertEqual(app.state.runs.get(completed.run_id).result, 42)
                # 遗留无调度队列的运行记录模拟进程未能提交终态。
                interrupted = app.state.runs.create(service_id=service.service_id,
                    instance_id=service.active_instance_id, version='1.0', revision=1, input=0)
                app.state.runs.update(interrupted.run_id, status='running')
                ciphertexts = app.state.store.read('credentials')
                self.assertNotIn(secret, json.dumps(ciphertexts))
                connection = app.state.store.connection
                self.assertTrue(connection.execute('SHOW fsync').fetchone()[0] == 'on')
                self.assertEqual(connection.execute('SHOW listen_addresses').fetchone()[0], '127.0.0.1')
                self.assertEqual(Path(connection.execute('SHOW data_directory').fetchone()[0]), self.directory / 'postgresql')
        self.assertFalse((self.directory / 'postgresql/postmaster.pid').exists())
        self.assertEqual((self.directory / 'secrets.json').stat().st_mode & 0o777, 0o600)
        with LocalPostgres(self.directory) as db, db.environment():
            app = create_app()
            async with app.router.lifespan_context(app):
                self.assertEqual(app.state.drafts.get(draft.draft_id).content['name'], 'saved draft')
                stored_env = app.state.environments.get(env.environment_id)
                reference = stored_env.connections[0].credential_ref
                self.assertEqual(app.state.credentials.resolve_for_transport(reference).get_secret_value(), secret)
                self.assertEqual(app.state.runs.get(completed.run_id).result, 42)
                self.assertEqual(app.state.runs.get(interrupted.run_id).error.code, 'APPLICATION_INTERRUPTED')
                self.assertEqual(app.state.services.get(service.service_id).active_instance_id, service.active_instance_id)
                self.assertEqual(len(app.state.services.history(service.service_id)), 2)
                third = app.state.services.save(ServiceWrite(name='v3', flow=flow), service.service_id)
                self.assertEqual(third.current.revision, 3)
                again = app.state.submission.submit(RunSubmit(service_id=service.service_id, input=9))
                await asyncio.wait_for(app.state.submission.queue.join(), 5)
                self.assertEqual(app.state.runs.get(again.run_id).result, 10)
        self.assertFalse((self.directory / 'postgresql/postmaster.pid').exists())

    async def test_directory_lock_and_database_lock(self):
        with LocalPostgres(self.directory) as db:
            with self.assertRaises(PlatformError):
                with LocalPostgres(self.directory):
                    self.fail('second owner must fail')
            first = PostgresStore(db.connection_url)
            try:
                with self.assertRaises(PlatformError):
                    PostgresStore(db.connection_url)
                first.write([('check', '1', {'value': 1})])
                self.assertEqual(first.read('check')['1']['value'], 1)
            finally:
                first.close()

    async def test_transaction_failure_and_disconnect_fail_closed(self):
        with LocalPostgres(self.directory) as db:
            store = PostgresStore(db.connection_url)
            # 第二条无法编码；第一条也必须回滚，不能发布半批文档。
            with self.assertRaises(PlatformError):
                store.write([('atomic', 'first', {'value': 1}), ('atomic', 'invalid', {'value': object()})])
            store.close()
            restored = PostgresStore(db.connection_url)
            self.assertEqual(restored.read('atomic'), {})
            restored.connection.close()
            with self.assertRaises(PlatformError):
                restored.write([('atomic', 'later', {'value': 2})])
            with self.assertRaises(PlatformError):
                restored.check()

    async def test_wrong_key_and_missing_key_preserve_data(self):
        with LocalPostgres(self.directory) as db, db.environment():
            app = create_app()
            app.state.credentials.put(SecretStr('synthetic-test-key'))
            app.state.store.close()
            original = (self.directory / 'secrets.json').read_bytes()
            with patch.dict(os.environ, {'AGENT_PLATFORM_CREDENTIAL_KEY': Fernet.generate_key().decode()}):
                with self.assertRaises(PlatformError):
                    create_app()
            self.assertEqual((self.directory / 'secrets.json').read_bytes(), original)
        (self.directory / 'secrets.json').rename(self.directory / 'saved-secrets.json')
        with self.assertRaises(PlatformError):
            with LocalPostgres(self.directory):
                self.fail('missing key must fail')
        self.assertTrue((self.directory / 'postgresql/PG_VERSION').is_file())
        self.assertFalse((self.directory / 'secrets.json').exists())

    async def test_no_implicit_memory_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PlatformError):
                configured_store()
        with patch.dict(os.environ, {'AGENT_PLATFORM_POSTGRES_BIN': '/nonexistent'}):
            with self.assertRaises(PlatformError):
                with LocalPostgres(self.directory):
                    self.fail('missing runtime must fail')
        self.assertFalse((self.directory / 'postgresql').exists())


if __name__ == '__main__':
    unittest.main()
