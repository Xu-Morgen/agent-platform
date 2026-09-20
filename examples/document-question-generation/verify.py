"""真实文档/本地 OCR/任务链路验收；模型响应由明确测试桩提供，不调用线上模型。"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.models import ModelResponse, ModelUsage
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.services import ServiceWrite
from agent_platform.preparation.manager import RuntimeManager
from agent_platform.storage import MemoryStore
from setup_service import assemble


async def verify(cache):
    root = Path(__file__).resolve().parent
    app = create_app(MemoryStore())
    app.state.catalog.blocks.manager = RuntimeManager(cache)
    try:
        read = await asyncio.to_thread(app.state.catalog.load, CatalogLoad(kind='block', path=str(root / 'read_document.py')))
        package = app.state.catalog.load(CatalogLoad(kind='package', path=str(root / 'document-question-generator')))
        artifact = app.state.catalog.artifact(read.resource_id)
        environment = app.state.environments.save(EnvironmentWrite(name='离线协议验收（非真实模型）', connections=[
            {'kind': 'model', 'connectionId': 'stub', 'baseUrl': 'https://example.invalid', 'model': 'offline-test'}]))
        draft = FlowDraft.model_validate(assemble(read.model_dump(by_alias=True), package.model_dump(by_alias=True), environment.environment_id, 'stub'))
        service = app.state.services.save(ServiceWrite(name='文档出题离线验收', flow=draft))
        valid = json.loads((root / 'contract-examples.json').read_text())['validOutput']
        calls, responses = [], []
        async def invoke(_adapter, connection, request):
            calls.append(request)
            return ModelResponse(output=responses.pop(0), usage=ModelUsage(input_tokens=100, output_tokens=100, quality='exact', source='offline-test'))
        with tempfile.TemporaryDirectory(prefix='document-question-') as directory:
            fixtures = Path(directory)
            references = {}
            subprocess.run([artifact.environment['python'], str(root / 'make_fixtures.py'), str(fixtures)], check=True, timeout=30)
            for filename in ('ordered.docx', 'text.pdf', 'scan.pdf', 'mixed.pdf', 'blank.pdf', 'corrupt.pdf'):
                path = fixtures / filename
                async def chunks():
                    yield path.read_bytes()
                reference = await app.state.files.save(filename, chunks())
                references[filename] = reference
                path.unlink()
                responses[:] = [{'questions': []}, deepcopy(valid)]
                calls.clear()
                task = app.state.submission.submit(RunSubmit(service_id=service.service_id,
                    input={'document': reference.model_dump(mode='json', by_alias=True)}))
                with patch('agent_platform.runtime.worker.OpenAIChatAdapter.invoke', invoke), patch(
                        'agent_platform.preparation.manager.httpx.Client', side_effect=AssertionError('完整缓存不可下载')):
                    await app.state.worker.execute(await app.state.submission.queue.get())
                result = app.state.runs.get(task.run_id)
                if filename in ('blank.pdf', 'corrupt.pdf'):
                    assert result.status == 'failed' and not calls, result
                else:
                    assert result.status == 'completed', result.error
                    assert len(calls) == 2, '格式失败必须只重试包'
                    assert sum(step.kind == 'block' for step in result.steps) == 1, '不得重做 OCR'
                    content = calls[0].messages[1].content
                    assert 'LASTPAGEUNIQUEFACT' in ''.join(content.upper().split()), content
                    assert calls[1].messages == calls[0].messages
                    if filename == 'mixed.pdf':
                        assert ''.join(content.upper().split()).count('VISIBLEHEADER') == 3, content
                    assert result.usage['tokens']['global']['totalTokens'] == 400
                print(json.dumps({'file': filename, 'status': result.status, 'modelCalls': len(calls),
                                  'error': result.error.code if result.error else None}, ensure_ascii=False), flush=True)
            # 资料不足是已记账的业务失败，不消耗额外格式重试。
            calls.clear()
            responses[:] = [{'error': 'INSUFFICIENT_INPUT'}]
            task = app.state.submission.submit(RunSubmit(service_id=service.service_id,
                input={'document': references['ordered.docx'].model_dump(mode='json', by_alias=True)}))
            with patch('agent_platform.runtime.worker.OpenAIChatAdapter.invoke', invoke):
                await app.state.worker.execute(await app.state.submission.queue.get())
            result = app.state.runs.get(task.run_id)
            assert result.status == 'failed' and result.error.code == 'PACKAGE_INPUT_INSUFFICIENT'
            assert len(calls) == 1 and result.usage['tokens']['global']['totalTokens'] == 200
            print('资料不足：一次调用后失败，用量已记录。', flush=True)
            # 第一页进度到达后通过真实任务取消入口停止扫描工作进程。
            from agent_platform.runtime.boundary import Boundary
            from agent_platform.runtime.cancellation import cancel_run
            calls.clear()
            task = app.state.submission.submit(RunSubmit(service_id=service.service_id,
                input={'document': references['scan.pdf'].model_dump(mode='json', by_alias=True)}))
            def cancel_after_page(phase, step):
                if phase == 'block_update' and any(s.kind == 'block' and s.progress and s.progress.get('current', 0) >= 1
                        for s in app.state.runs.get(task.run_id).steps):
                    cancel_run(app.state.submission, task.run_id)
            app.state.worker.boundary_factory = lambda: Boundary(observer=cancel_after_page)
            with patch('agent_platform.runtime.worker.OpenAIChatAdapter.invoke', invoke):
                await app.state.worker.execute(await app.state.submission.queue.get())
            result = app.state.runs.get(task.run_id)
            assert result.status == 'cancelled' and not calls and result.result is None
            print('扫描中取消：工作进程已退出，未进入出题。', flush=True)
        print('真实文件/OCR与离线协议验收通过；未进行模型业务质量验收。')
    finally:
        app.state.catalog.close()
        app.state.files.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, required=True)
    asyncio.run(verify(parser.parse_args().cache_dir))
