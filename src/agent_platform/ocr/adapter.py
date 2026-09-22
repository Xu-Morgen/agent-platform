"""固定适配的 RapidOCR ONNX CPU 识别；不执行模型目录中的代码。"""
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform

from ..contracts.ocr import OCRManifest
from ..contracts.errors import ErrorResponse, PlatformError

BATCH_SIZE = 8
THREADS = 2
MAX_MODEL_BYTES = 512 * 1024 * 1024


def failure(code, message):
    return PlatformError(ErrorResponse(code=code, stage='ocr', message=message), 422)


def read_manifest(root):
    try:
        return OCRManifest.model_validate_json((Path(root) / 'ocr.json').read_bytes())
    except (ValueError, OSError):
        raise failure('OCR_INCOMPATIBLE', '缺少 ocr.json 或模型清单不符合契约') from None


def verify_files(root, manifest):
    try:
        root = Path(root).resolve(strict=True)
    except OSError:
        raise failure('OCR_NOT_READY', '模型目录不存在或不可读取') from None
    total = 0
    for item in (manifest.detection, manifest.recognition, manifest.classification):
        path = root / item.path
        try:
            if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
                raise ValueError()
            path.resolve(strict=True).relative_to(root)
            size = path.stat().st_size
            if not path.is_file() or size <= 0 or size > MAX_MODEL_BYTES:
                raise ValueError()
            digest = sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != item.sha256:
                raise ValueError()
            total += size
        except (OSError, ValueError):
            raise failure('OCR_NOT_READY', f'模型文件缺失、损坏或路径不受支持：{item.path}') from None
    if total > MAX_MODEL_BYTES:
        raise failure('OCR_INPUT_LIMIT', '模型文件合计超过 512 MiB')
    return total


class RapidOCREngine:
    def __init__(self, root, manifest):
        from packaging.specifiers import SpecifierSet
        import onnx
        from rapidocr_onnxruntime import RapidOCR
        verify_files(root, manifest)
        required = {'rapidocr-onnxruntime', 'onnxruntime', 'numpy', 'onnx', 'pillow', 'opencv-python', 'pyclipper', 'shapely', 'pyyaml', 'six'}
        if (set(manifest.runtime) != required or platform.system() != 'Linux'
                or platform.machine() != 'x86_64'
                or platform.python_version() not in SpecifierSet(manifest.python)
                or any(version(name) != value for name, value in manifest.runtime.items())):
            raise failure('OCR_INCOMPATIBLE', 'OCR 运行依赖或 Python/平台与清单不一致')
        root = Path(root)
        try:
            for item in (manifest.detection, manifest.recognition, manifest.classification):
                graph = onnx.load(str(root / item.path), load_external_data=False)
                tensors = list(graph.graph.initializer)
                for sparse in graph.graph.sparse_initializer:
                    tensors.extend((sparse.values, sparse.indices))
                for node in graph.graph.node:
                    for attribute in node.attribute:
                        if attribute.HasField('t'):
                            tensors.append(attribute.t)
                        tensors.extend(attribute.tensors)
                if (graph.functions or any(t.data_location == onnx.TensorProto.EXTERNAL for t in tensors)
                        or any(n.domain not in ('', 'ai.onnx') or any(a.HasField('g') or a.graphs for a in n.attribute)
                               for n in graph.graph.node)):
                    raise ValueError()
                if item == manifest.recognition and not any(p.key == 'character' and p.value for p in graph.metadata_props):
                    raise ValueError('识别模型必须内嵌字典')
                onnx.checker.check_model(graph)
            self.engine = RapidOCR(det_model_path=str(root / manifest.detection.path),
                rec_model_path=str(root / manifest.recognition.path), cls_model_path=str(root / manifest.classification.path),
                intra_op_num_threads=1, inter_op_num_threads=1, text_score=0.0)
        except Exception:
            raise failure('OCR_INCOMPATIBLE', 'OCR 模型须为受支持的内嵌 ONNX 组合，识别模型须内嵌字典；不支持外部张量、自定义算子或子图') from None

    def recognize(self, image, use_classification):
        result, _ = self.engine(image, use_cls=use_classification)
        return result or []


def image_bytes(request):
    import base64
    import io
    from PIL import Image
    try:
        data = base64.b64decode(request.image_base64, validate=True)
        if len(data) > 9 * 1024 * 1024:
            raise ValueError()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if (image.format != 'PNG' or image.mode != 'RGB' or max(width, height) > 6000
                    or width * height > 20000000 or getattr(image, 'n_frames', 1) != 1):
                raise ValueError()
            image.verify()
        return data, width, height
    except Exception:
        raise failure('OCR_INPUT_LIMIT', 'OCR 仅接受单帧 RGB PNG，最多 9 MiB、6000 边长及 2000 万像素') from None
