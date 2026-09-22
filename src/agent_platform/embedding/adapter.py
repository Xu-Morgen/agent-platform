"""明确适配的 BERT ONNX CPU 编码；不执行模型目录中的代码。"""
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

from ..contracts.embedding import EmbeddingManifest
from ..contracts.errors import ErrorResponse, PlatformError

BATCH_SIZE = 8
THREADS = 2
MAX_MODEL_BYTES = 512 * 1024 * 1024


def failure(code, message):
    return PlatformError(ErrorResponse(code=code, stage='embedding', message=message), 422)


def read_manifest(root):
    try:
        return EmbeddingManifest.model_validate_json((Path(root) / 'embedding.json').read_bytes())
    except (ValueError, OSError):
        raise failure('EMBEDDING_INCOMPATIBLE', '缺少 embedding.json 或模型清单不符合契约') from None


def verify_files(root, manifest):
    root = Path(root).resolve(strict=True)
    total = 0
    for item in (manifest.weights, manifest.tokenizer, manifest.configuration):
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
            raise failure('EMBEDDING_NOT_READY', f'模型文件缺失、损坏或路径不受支持：{item.path}') from None
    if total > MAX_MODEL_BYTES:
        raise failure('EMBEDDING_INPUT_LIMIT', '模型文件合计超过 512 MiB')
    return total


class BertOnnxEncoder:
    def __init__(self, root, manifest):
        from packaging.specifiers import SpecifierSet
        import numpy as np
        import onnx
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np, self.manifest = np, manifest
        root = Path(root)
        verify_files(root, manifest)
        required = {'numpy', 'onnx', 'onnxruntime', 'tokenizers'}
        if (set(manifest.runtime) != required or platform.system() != 'Linux'
                or platform.machine() != 'x86_64'
                or platform.python_version() not in SpecifierSet(manifest.python)
                or any(version(name) != value for name, value in manifest.runtime.items())):
            raise failure('EMBEDDING_INCOMPATIBLE', '模型运行依赖或 Python/平台与清单不一致')
        try:
            config = json.loads((root / manifest.configuration.path).read_text())
            if (config.get('model_type') != 'bert' or config.get('hidden_size') != manifest.dimensions
                    or config.get('max_position_embeddings', 0) < manifest.max_tokens):
                raise ValueError()
            graph = onnx.load(str(root / manifest.weights.path), load_external_data=False)
            if (any(t.data_location == onnx.TensorProto.EXTERNAL for t in graph.graph.initializer)
                    or any(n.domain not in ('', 'ai.onnx') or n.attribute and any(a.HasField('g') or a.graphs for a in n.attribute)
                           for n in graph.graph.node)):
                raise ValueError()
            onnx.checker.check_model(graph)
            del graph
            self.tokenizer = Tokenizer.from_file(str(root / manifest.tokenizer.path))
            self.tokenizer.no_truncation()
            self.tokenizer.no_padding()
            self.pad_id = self.tokenizer.token_to_id('[PAD]')
            if self.pad_id is None or self.tokenizer.token_to_id('[CLS]') is None:
                raise ValueError()
            options = ort.SessionOptions()
            options.intra_op_num_threads = THREADS
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            self.session = ort.InferenceSession(str(root / manifest.weights.path), sess_options=options,
                                                providers=['CPUExecutionProvider'])
            self.inputs = {item.name for item in self.session.get_inputs()}
            if self.inputs != {'input_ids', 'attention_mask', 'token_type_ids'}:
                raise ValueError()
            if any(item.type != 'tensor(int64)' for item in self.session.get_inputs()):
                raise ValueError()
            output = self.session.get_outputs()[0]
            if output.type != 'tensor(float)' or len(output.shape) != 3 or output.shape[2] != manifest.dimensions:
                raise ValueError()
            self.output = output.name
        except Exception as exc:
            if isinstance(exc, PlatformError):
                raise
            raise failure('EMBEDDING_INCOMPATIBLE', '仅支持完整内嵌权重的 BERT ONNX、int64 三输入与 float32 token 输出') from None

    def tokens(self, text, purpose):
        instruction = self.manifest.query_instruction if purpose == 'query' else self.manifest.document_instruction
        encoded = self.tokenizer.encode(instruction + text)
        if len(encoded.ids) > self.manifest.max_tokens:
            raise failure('EMBEDDING_INPUT_LIMIT', '文本含指令及特殊 token 后超过模型上限；请显式切分片段或缩短查询')
        return encoded

    def split(self, text):
        """返回无遗漏的字符边界；每段重新编码核对，绝不截断 tokenizer 输入。"""
        if not text or len(text) > 20000:
            raise failure('EMBEDDING_INPUT_LIMIT', '切分正文须为 1～20000 字符')
        result, start = [], 0
        while start < len(text):
            tail = text[start:]
            try:
                self.tokens(tail, 'document')
                result.append((start, len(text)))
                break
            except PlatformError:
                offsets = self.tokenizer.encode(tail, add_special_tokens=False).offsets
                capacity = self.manifest.max_tokens - len(self.tokenizer.encode(self.manifest.document_instruction).ids)
                if capacity < 1 or not offsets:
                    raise failure('EMBEDDING_INPUT_LIMIT', '模型指令未留下正文容量，无法保留定位切分') from None
                end = offsets[min(capacity, len(offsets)) - 1][1]
                while end > 0:
                    try:
                        self.tokens(tail[:end], 'document')
                        break
                    except PlatformError:
                        end = next((a for a, b in reversed(offsets) if 0 < a < end), 0)
                if end <= 0:
                    raise failure('EMBEDDING_INPUT_LIMIT', '无法按 tokenizer 边界保留字符定位')
                result.append((start, start + end))
                start += end
        return result

    def encode(self, texts, purpose='document'):
        np = self.np
        if len(texts) > BATCH_SIZE or purpose not in ('document', 'query'):
            raise failure('EMBEDDING_INPUT_LIMIT', '编码批次或用途无效')
        encoded = [self.tokens(text, purpose) for text in texts]
        if not encoded:
            return np.empty((0, self.manifest.dimensions), dtype=np.float32), 0
        width = max(len(item.ids) for item in encoded)
        ids = np.full((len(encoded), width), self.pad_id, dtype=np.int64)
        mask = np.zeros_like(ids)
        types = np.zeros_like(ids)
        for i, item in enumerate(encoded):
            ids[i, :len(item.ids)] = item.ids
            mask[i, :len(item.ids)] = 1
            types[i, :len(item.ids)] = item.type_ids
        try:
            output = self.session.run([self.output], dict(input_ids=ids, attention_mask=mask, token_type_ids=types))[0]
            if output.shape != (len(texts), width, self.manifest.dimensions) or not np.isfinite(output).all():
                raise ValueError()
            vectors = output[:, 0, :] if self.manifest.pooling == 'cls' else (output * mask[:, :, None]).sum(1) / mask.sum(1)[:, None]
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if not np.isfinite(norms).all() or (norms <= 1e-12).any():
                raise ValueError()
            return (vectors / norms).astype(np.float32), sum(len(item.ids) for item in encoded)
        except Exception:
            raise failure('EMBEDDING_INFERENCE_ERROR', '本地推理失败或返回向量数量、维度、数值、范数无效') from None
