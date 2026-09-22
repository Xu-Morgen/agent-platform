"""OCR 工作进程；stdout 仅承载协议，模型与图片随进程释放。"""
import base64
import contextlib
from hashlib import sha256
import io
import json
import resource
import sys
from time import perf_counter

from ..contracts.ocr import OCRSnapshot, OCRRequest, OCRResult, OCRLine, OCRPoint
from ..contracts.errors import PlatformError
from .adapter import RapidOCREngine, failure, image_bytes


class Engine:
    def __init__(self, root, snapshot):
        self.snapshot = snapshot
        start = perf_counter()
        self.engine = RapidOCREngine(root, snapshot.manifest)
        self.load_seconds = perf_counter() - start

    def recognize(self, payload):
        request = OCRRequest.model_validate(payload)
        data, width, height = image_bytes(request)
        start = perf_counter()
        items = self.engine.recognize(data, request.use_classification)
        lines = [OCRLine(points=[OCRPoint(x=float(x), y=float(y)) for x, y in box],
                         text=str(text), confidence=float(score)) for box, text, score in items]
        return OCRResult(model_id=self.snapshot.model_id, image_sha256=sha256(data).hexdigest(),
            width=width, height=height, lines=lines, inference_seconds=perf_counter() - start)

    def diagnostic(self):
        import cv2
        import numpy as np
        from PIL import Image
        # Synthetic text exercises detection, recognition and optional classification.
        image = np.full((140, 640, 3), 255, dtype=np.uint8)
        cv2.putText(image, 'OCR TEST 123', (25, 90), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
        stream = io.BytesIO()
        Image.fromarray(image).save(stream, format='PNG')
        result = self.recognize(OCRRequest(image_base64=base64.b64encode(stream.getvalue()).decode(), use_classification=True))
        text = ' '.join(line.text for line in result.lines).strip()
        if not text or not any('123' in line.text for line in result.lines):
            raise failure('OCR_INCOMPATIBLE', 'OCR 小样例未识别预期数字，模型组合不可用')
        return dict(recognizedText=text, loadSeconds=self.load_seconds, inferenceSeconds=result.inference_seconds,
                    peakMemoryBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def main():
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    engine, channel = None, sys.stdout
    for line in sys.stdin:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                message = json.loads(line)
                if engine is None:
                    engine = Engine(message['root'], OCRSnapshot.model_validate(message['snapshot']))
                    value = {'ready': True}
                elif message['operation'] == 'diagnostic':
                    value = engine.diagnostic()
                elif message['operation'] == 'recognize':
                    value = engine.recognize(message['request']).model_dump(mode='json', by_alias=True)
                else:
                    raise failure('OCR_INCOMPATIBLE', '未知 OCR 操作')
            response = {'value': value}
        except PlatformError as exc:
            response = {'error': exc.error.model_dump(mode='json', by_alias=True)}
        except Exception:
            response = {'error': failure('OCR_INFERENCE_ERROR', 'OCR 工作进程请求或执行失败').error.model_dump(mode='json', by_alias=True)}
        channel.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + '\n')
        channel.flush()


if __name__ == '__main__':
    main()
