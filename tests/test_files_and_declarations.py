"""文件持久化与静态声明的轻量边界验证。"""
import asyncio
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from agent_platform.contracts.errors import PlatformError
from agent_platform.contracts.files import TaskFile
from agent_platform.contracts.base import StrictModel
from agent_platform.registry.declarations import read_declaration
from agent_platform.storage import MemoryStore
from agent_platform.storage.files import TaskFiles, file_references


async def chunks(data):
    for offset in range(0, len(data), 7):
        yield data[offset:offset + 7]


class Declarations(unittest.TestCase):
    def test_never_executes_source(self):
        source = b'''from agent_platform.blocks import block
raise RuntimeError('not executed')
@block(id='sample', version='1.0.0', name='Sample', dependencies=['httpx==0.28.1'])
def run(value: str) -> str: return value
'''
        self.assertEqual(read_declaration(source).dependencies, ['httpx==0.28.1'])
        with self.assertRaises(PlatformError):
            read_declaration(source.replace(b"['httpx==0.28.1']", b"__import__('os').system('exit 1')"))

    def test_download_declarations(self):
        from agent_platform.contracts.dependencies import RuntimeDeclaration
        from pydantic import ValidationError
        valid = dict(dependencies=['example==1.0'], dependencySources=[dict(kind='wheel',package='example',url='https://example.com/example.whl',sha256='a'*64)])
        self.assertEqual(RuntimeDeclaration.model_validate(valid).dependencies, ['example==1.0'])
        for url in ['http://example.com/x.whl', 'https://user:secret@example.com/x.whl', 'https://example.com/x.whl?token=secret']:
            with self.assertRaises(ValidationError):
                RuntimeDeclaration.model_validate({**valid, 'dependencySources': [{**valid['dependencySources'][0], 'url': url}]})


class Files(unittest.IsolatedAsyncioTestCase):
    async def test_saved_copy_and_restart(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory() as root:
            files = TaskFiles(store, root)
            reference = await files.save('example.pdf', chunks(b'%PDF-1.7\nexample'))
            with files.lock:
                documents = files.bindings([reference], 'run_one')
                store.write(documents)
                files.accept_bindings(documents)
            restored = TaskFiles(store, root)
            self.assertEqual(restored.resolve(reference, run_id='run_one').read_bytes(), b'%PDF-1.7\nexample')
            with self.assertRaises(PlatformError): restored.resolve(reference, run_id='run_other')
            with self.assertRaises(PlatformError): restored.remove(reference.file_id)
            restored.resolve(reference).write_bytes(b'damaged')
            with self.assertRaises(PlatformError) as error: restored.resolve(reference)
            self.assertEqual(error.exception.error.code, 'FILE_REFERENCE_INVALID')

    async def test_format_limit_and_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            files = TaskFiles(MemoryStore(), root, max_bytes=20)
            for name, data, code in [('fake.pdf', b'not a PDF', 'FILE_FORMAT_UNSUPPORTED'), ('huge.pdf', b'%PDF-' + b'a'*30, 'FILE_TOO_LARGE'), ('../file.pdf', b'%PDF-1.7', 'FILE_FORMAT_UNSUPPORTED')]:
                with self.assertRaises(PlatformError) as error: await files.save(name, chunks(data))
                self.assertEqual(error.exception.error.code, code)
                self.assertEqual(list(Path(root).iterdir()), [])
            reference = await files.save('valid.pdf', chunks(b'%PDF-1.7'))
            files.remove(reference.file_id)
            with self.assertRaises(PlatformError): files.resolve(reference)

    async def test_docx_and_marked_fields(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('word/document.xml', '<document/>')
        with tempfile.TemporaryDirectory() as root:
            files = TaskFiles(MemoryStore(), root)
            reference = await files.save('example.docx', chunks(stream.getvalue()))
            class Input(StrictModel):
                attachment: TaskFile | None = None
            value = Input(attachment=reference).model_dump(mode='json', by_alias=True)
            self.assertEqual(file_references(Input.model_json_schema(), value), [reference])


class Processes(unittest.IsolatedAsyncioTestCase):
    async def test_child_execution_and_real_validators(self):
        import os
        from agent_platform.preparation.manager import RuntimeManager
        from agent_platform.registry.single_blocks import SingleBlockRegistry
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'block.py'
            path.write_text('''import os
from pydantic import field_validator
from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel
class Input(StrictModel):
    text: str
    @field_validator('text')
    @classmethod
    def content(cls, value):
        if value == 'invalid': raise ValueError('拒绝该输入')
        return value
@block(id='pid', version='1.0.0', name='PID')
def run(value: Input) -> int: return os.getpid()
''')
            artifact = SingleBlockRegistry(manager=RuntimeManager(Path(root) / 'cache')).load(path)
            self.assertNotEqual(await artifact.invoke({'text': 'hello'}), os.getpid())
            with self.assertRaises(PlatformError): artifact.input_adapter.validate_python({'text': 'invalid'})
            self.assertIn('x-runtime-contract', artifact.input_adapter.json_schema())

    async def test_cpu_process_can_be_cancelled(self):
        from agent_platform.preparation.manager import RuntimeManager
        from agent_platform.registry.single_blocks import SingleBlockRegistry
        from agent_platform.runtime.boundary import current_boundary, Boundary
        from agent_platform.contracts.errors import ErrorResponse
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'block.py'
            path.write_text('''from agent_platform.blocks import block
@block(id='cpu', version='1.0.0', name='CPU')
def run(value: int) -> int:
    while True: value += 1
''')
            artifact = SingleBlockRegistry(manager=RuntimeManager(Path(root) / 'cache')).load(path)
            checks = 0
            def cancel(phase, step):
                nonlocal checks
                if phase == 'block_update':
                    checks += 1
                    if checks >= 3:
                        raise PlatformError(ErrorResponse(code='RUN_CANCELLED', stage='test', message='取消'))
            token = current_boundary.set(Boundary(observer=cancel))
            try:
                with self.assertRaises(PlatformError) as error:
                    await asyncio.wait_for(artifact.invoke(0), 5)
                self.assertEqual(error.exception.error.code, 'RUN_CANCELLED')
            finally: current_boundary.reset(token)

    async def test_api_bridge_keeps_runtime_validation(self):
        from agent_platform.preparation.manager import RuntimeManager
        from agent_platform.registry.single_blocks import SingleBlockRegistry
        class API:
            async def request(self, method, payload, *, response_type): return {'text': ' Hello  WORLD '}
        with tempfile.TemporaryDirectory() as root:
            artifact = SingleBlockRegistry(manager=RuntimeManager(root)).load('samples/blocks/complete.py')
            result = await artifact.invoke({'query': 'hello'}, api=API())
            self.assertEqual(result, {'text': 'Hello WORLD', 'characterCount': 11, 'changed': True})


class Cache(unittest.TestCase):
    def test_cached_model_offline_and_corruption(self):
        from agent_platform.preparation.manager import RuntimeManager, Preparation
        from hashlib import sha256
        from unittest.mock import patch
        import httpx
        content = b'model fixture'
        digest = sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            manager = RuntimeManager(root)
            blob = Path(root) / 'blobs' / digest
            blob.parent.mkdir()
            blob.write_bytes(content)
            with patch('agent_platform.preparation.manager.httpx.Client', side_effect=AssertionError('offline')):
                self.assertEqual(manager.download('https://example.com/model', digest, Preparation()), blob)
            blob.write_bytes(b'corrupt')
            client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content)))
            with patch('agent_platform.preparation.manager.httpx.Client', return_value=client):
                self.assertEqual(manager.download('https://example.com/model', digest, Preparation()).read_bytes(), content)
            blob.unlink()
            client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'wrong')))
            with patch('agent_platform.preparation.manager.httpx.Client', return_value=client):
                with self.assertRaises(PlatformError) as error:
                    manager.download('https://example.com/model', digest, Preparation())
                self.assertEqual(error.exception.error.code, 'PREPARATION_HASH_MISMATCH')
                self.assertFalse(blob.exists())
                self.assertEqual(list(blob.parent.glob('*.part')), [])


class ApplicationFiles(unittest.IsolatedAsyncioTestCase):
    async def test_upload_submit_execute_and_restore_without_source(self):
        import httpx
        from agent_platform.application import create_app
        from agent_platform.contracts.catalog import CatalogLoad
        from agent_platform.contracts.flows import FlowDraft
        from agent_platform.contracts.services import ServiceWrite
        from agent_platform.preparation.manager import RuntimeManager
        from agent_platform.repositories.runs import RunRepository
        with tempfile.TemporaryDirectory() as root:
            store = MemoryStore()
            app = create_app(store)
            app.state.catalog.blocks.manager = RuntimeManager(Path(root) / 'runtime')
            app.state.files.close()
            files = TaskFiles(store, Path(root) / 'files')
            app.state.files = app.state.submission.files = files
            block = Path(root) / 'file.py'
            block.write_text('''from agent_platform.blocks import block, BlockContext
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.files import TaskFile
class Input(StrictModel):
    document: TaskFile
@block(id='file-reader', version='1.0.0', name='文件读取')
def run(value: Input, *, context: BlockContext) -> int:
    context.progress('读取文件', current=1, total=1)
    return context.file(value.document).stat().st_size
''')
            view = app.state.catalog.load(CatalogLoad(kind='block', path=str(block)))
            draft = FlowDraft(name='file', input_contract=view.input_contract, output_contract=view.output_contract,
                              flow=[{'kind':'block','nodeId':'read','artifactRef':view.resource_id}])
            service = app.state.services.save(ServiceWrite(name='file', flow=draft))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/v1/files?name=sample.pdf', content=b'%PDF-1.7\nexample')
                self.assertEqual(response.status_code, 201, response.text)
                reference = response.json()
                response = await client.post('/api/v1/runs', json={'serviceId':service.service_id, 'input':{'document':reference}})
                self.assertEqual(response.status_code, 202, response.text)
                run_id = response.json()['runId']
                block.unlink()
                await app.state.worker.execute(await app.state.submission.queue.get())
                run = app.state.runs.get(run_id)
                self.assertEqual(run.status, 'completed', run.error)
                self.assertEqual(run.result, 16)
                self.assertEqual(next(s for s in run.steps if s.kind == 'block').progress['message'], '读取文件')
                self.assertEqual((await client.delete('/api/v1/files/' + reference['fileId'])).status_code, 422)
            restored = TaskFiles(store, Path(root) / 'files')
            self.assertEqual(restored.resolve(reference, run_id=run_id).read_bytes(), b'%PDF-1.7\nexample')
            self.assertEqual(RunRepository(store).get(run_id).input['document'], reference)
            app.state.catalog.close()


class PreparationFailures(unittest.TestCase):
    def test_download_errors_are_specific_and_leave_no_enabled_blob(self):
        import errno
        import httpx
        from unittest.mock import patch
        from agent_platform.preparation.manager import RuntimeManager, Preparation
        with tempfile.TemporaryDirectory() as root:
            manager = RuntimeManager(root)
            cases = [
                (lambda request: httpx.Response(404), 'PREPARATION_URL_ERROR'),
                (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('timeout')), 'PREPARATION_TIMEOUT'),
                (lambda request: (_ for _ in ()).throw(httpx.ConnectError('offline')), 'PREPARATION_NETWORK_ERROR'),
            ]
            for handler, code in cases:
                client = httpx.Client(transport=httpx.MockTransport(handler))
                with patch('agent_platform.preparation.manager.httpx.Client', return_value=client):
                    with self.assertRaises(PlatformError) as error:
                        manager.download('https://example.com/model', 'a'*64, Preparation())
                    self.assertEqual(error.exception.error.code, code)
                self.assertEqual(list((Path(root)/'blobs').iterdir()), [])
            with patch.object(manager, '_prepare', side_effect=OSError(errno.ENOSPC, 'full')):
                with self.assertRaises(PlatformError) as error: manager.prepare(None)
                self.assertEqual(error.exception.error.code, 'PREPARATION_DISK_FULL')

    def test_concurrent_prepare_and_cancelled_mutex(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from agent_platform.preparation.manager import RuntimeManager, Preparation
        from agent_platform.blocks.single import BlockMetadata
        with tempfile.TemporaryDirectory() as root:
            manager = RuntimeManager(root)
            metadata = BlockMetadata(id='plain', version='1.0.0', name='并发缓存')
            with ThreadPoolExecutor(max_workers=3) as executor:
                results = list(executor.map(lambda _: manager.prepare(metadata), range(3)))
            self.assertEqual(len({result['key'] for result in results}), 1)
            self.assertEqual(len(list(Path(root).glob('*.json'))), 1)
            cancelled = threading.Event(); cancelled.set()
            with self.assertRaises(PlatformError) as error:
                manager.prepare(metadata, operation=Preparation(cancel=cancelled))
            self.assertEqual(error.exception.error.code, 'PREPARATION_CANCELLED')


if __name__ == '__main__': unittest.main()
