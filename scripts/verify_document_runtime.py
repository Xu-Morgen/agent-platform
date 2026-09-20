"""显式执行的真实 OCR 小样本验收，会下载依赖和模型；须先获得安装授权。"""
import argparse
import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.runs import RunSubmit
from agent_platform.preparation.manager import RuntimeManager, Preparation
from agent_platform.storage import MemoryStore

# 官方 RapidAI default_models.yaml，核对日期 2026-09-20。
# https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml
MODEL_BASE = 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/'
MODELS = [
    dict(name='det', version='PP-OCRv4-mobile-v3.9.2', url=MODEL_BASE+'det/ch_PP-OCRv4_det_mobile.onnx',
         sha256='d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9', filename='det.onnx'),
    dict(name='rec', version='PP-OCRv4-mobile-v3.9.2', url=MODEL_BASE+'rec/ch_PP-OCRv4_rec_mobile.onnx',
         sha256='48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b', filename='rec.onnx'),
    dict(name='cls', version='PP-OCRv4-mobile-v3.9.2', url=MODEL_BASE+'cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx',
         sha256='e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c', filename='cls.onnx'),
]


def block_source():
    return '''import socket
import pymupdf
from rapidocr_onnxruntime import RapidOCR
from agent_platform.blocks import block, BlockContext
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.files import TaskFile
class Input(StrictModel):
    document: TaskFile
@block(id='verify-ocr', version='1.0.0', name='真实扫描 PDF 验收',
       dependencies=['rapidocr-onnxruntime==1.4.4', 'onnxruntime==1.23.2', 'PyMuPDF==1.26.7'],
       models=MODELS_LITERAL)
def run(value: Input, *, context: BlockContext) -> str:
    def no_network(*args, **kwargs):
        raise RuntimeError('OCR 运行阶段不得联网')
    socket.socket.connect = no_network
    engine = RapidOCR(det_model_path=str(context.model('det')),
                      rec_model_path=str(context.model('rec')),
                      cls_model_path=str(context.model('cls')),
                      intra_op_num_threads=1, inter_op_num_threads=1)
    texts = []
    with pymupdf.open(context.file(value.document)) as document:
        for index, page in enumerate(document):
            if page.get_text().strip(): raise ValueError('验收输入必须是真实扫描页')
            result, _ = engine(page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes('png'))
            if not result: raise ValueError('OCR 未识别到正文')
            texts.extend(item[1] for item in result)
            context.progress('OCR 页面已完成', current=index + 1, total=len(document))
    return '\\n'.join(texts)
'''.replace('MODELS_LITERAL', repr(MODELS))


async def verify(cache):
    with tempfile.TemporaryDirectory(prefix='agent-ocr-verify-') as root:
        app = create_app(MemoryStore())
        manager = RuntimeManager(cache)
        app.state.catalog.blocks.manager = manager
        path = Path(root) / 'ocr.py'
        path.write_text(block_source())
        operation = Preparation(progress=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
        try:
            view = await asyncio.to_thread(app.state.catalog.load, CatalogLoad(kind='block', path=str(path)), operation=operation)
            artifact = app.state.catalog.artifact(view.resource_id)
            fixture = Path(root) / 'scan.pdf'
            subprocess.run([artifact.environment['python'], '-c', '''import pymupdf, sys
source = pymupdf.open()
page = source.new_page(width=600, height=160)
page.insert_text((35, 80), 'PLATFORM OCR TEST 2026', fontsize=26)
image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes('png')
scan = pymupdf.open()
page = scan.new_page(width=600, height=160)
page.insert_image(page.rect, stream=image)
scan.save(sys.argv[1])
''', str(fixture)], check=True, timeout=30)
            async def chunks():
                with fixture.open('rb') as source:
                    while chunk := source.read(65536): yield chunk
            reference = await app.state.files.save(fixture.name, chunks())
            fixture.unlink()
            path.unlink()
            draft = FlowDraft(name='OCR 验收', input_contract=view.input_contract, output_contract=view.output_contract,
                              flow=[{'kind':'block','nodeId':'ocr','artifactRef':view.resource_id}])
            service = app.state.services.save(ServiceWrite(name='OCR 验收', flow=draft))
            run = app.state.submission.submit(RunSubmit(service_id=service.service_id, input={'document':reference.model_dump(mode='json', by_alias=True)}))
            await app.state.worker.execute(await app.state.submission.queue.get())
            result = app.state.runs.get(run.run_id)
            if result.status != 'completed': raise RuntimeError(result.error.model_dump_json())
            if 'PLATFORMOCRTEST2026' not in ''.join(result.result.upper().split()):
                raise AssertionError('识别结果不符：' + result.result)
            # 缓存复用时禁用平台下载连接，OCR 块自身也禁用网络。
            from unittest.mock import patch
            with patch('agent_platform.preparation.manager.httpx.Client', side_effect=AssertionError('离线验收不能发起下载')):
                second = app.state.submission.submit(RunSubmit(service_id=service.service_id, input=run.input))
                await app.state.worker.execute(await app.state.submission.queue.get())
                offline = app.state.runs.get(second.run_id)
                if offline.status != 'completed' or offline.result != result.result:
                    raise AssertionError('完整缓存离线执行失败')
            print(json.dumps({'status':'passed','text':result.result,'runtimeKey':artifact.environment['key'], 'offline':True}, ensure_ascii=False))
        finally:
            app.state.files.close()
            app.state.catalog.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(verify(args.cache_dir))
