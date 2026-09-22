"""任务独占的本地编码进程；向量只驻留此进程，不进入 JSON 通道。"""
import json
import resource
import sys
from time import perf_counter

from ..contracts.embedding import EmbeddingSnapshot, SemanticSearchRequest, SemanticSearchResult, SemanticSearchStats
from ..contracts.errors import PlatformError
from .adapter import BertOnnxEncoder, BATCH_SIZE, failure


class Engine:
    def __init__(self, root, snapshot):
        self.snapshot = snapshot
        started = perf_counter()
        self.encoder = BertOnnxEncoder(root, snapshot.manifest)
        self.load_seconds = perf_counter() - started
        self.cache = {}

    def search(self, request):
        request = SemanticSearchRequest.model_validate(request)
        encoder, np = self.encoder, self.encoder.np
        # 查询超限与任一片段超限先失败，不产生部分搜索结果。
        encoder.tokens(request.query, 'query')
        for item in request.fragments:
            encoder.tokens(item.text, 'document')
        keys = [(self.snapshot.model_id, item.version_id, item.reader, request.splitter, item.sha256, 'document')
                for item in request.fragments]
        missing = list(dict.fromkeys(key for key in keys if key not in self.cache))
        if len(self.cache) + len(missing) > 2000:
            raise failure('EMBEDDING_CAPACITY_EXCEEDED', '单任务最多缓存 2000 个不同片段，不缩小检索范围')
        texts = {key: item.text for key, item in zip(keys, request.fragments)}
        hits = sum(key in self.cache for key in keys)
        document_tokens = batches = 0
        started = perf_counter()
        for offset in range(0, len(missing), BATCH_SIZE):
            batch = missing[offset:offset + BATCH_SIZE]
            vectors, count = encoder.encode([texts[key] for key in batch])
            # encode 已完成整批数值校验，才发布此批缓存。
            self.cache.update(zip(batch, vectors))
            document_tokens += count
            batches += 1
        query, query_tokens = encoder.encode([request.query], 'query')
        batches += 1
        scores = [float(np.clip(np.dot(self.cache[key], query[0]), -1, 1)) for key in keys]
        order = sorted(range(len(keys)), key=lambda i: -scores[i])
        candidates = [item.model_copy(update={'score': scores[i]}) for i in order
                      if (request.minimum_score is None or scores[i] >= request.minimum_score)
                      for item in [request.fragments[i]]][:request.top_k]
        return SemanticSearchResult(reference=request.reference, model=self.snapshot, splitter=request.splitter,
            scope_limited=request.scope_limited, candidates=candidates,
            stats=SemanticSearchStats(document_tokens=document_tokens, query_tokens=query_tokens,
                encoded_fragments=len(missing), cache_hits=hits, batches=batches, queue_seconds=0.0,
                inference_seconds=perf_counter() - started)).model_dump(mode='json', by_alias=True)

    def split_corpus(self, payload):
        from hashlib import sha256
        request = SemanticSearchRequest.model_validate(payload)
        fragments = []
        for item in request.fragments:
            offsets = self.encoder.split(item.text)
            for start, end in offsets:
                if len(offsets) == 1:
                    fragments.append(item)
                else:
                    text = item.text[start:end]
                    locator = f'{item.locator}; chars[{start}:{end}]'
                    if len(locator) > 300:
                        raise failure('EMBEDDING_INPUT_LIMIT', '切分后定位超过 300 字符，无法完整保留来源')
                    identity = sha256(f'{item.fragment_id}:{start}:{end}'.encode()).hexdigest()
                    fragments.append(item.model_copy(update={'text': text, 'sha256': sha256(text.encode()).hexdigest(),
                        'fragment_id': 'sem_' + identity, 'locator': locator}))
            if len(fragments) > 500:
                raise failure('EMBEDDING_INPUT_LIMIT', 'tokenizer 切分后超过 500 片段，不缩小资料范围')
        return SemanticSearchRequest(**{**request.model_dump(), 'fragments': fragments}).model_dump(mode='json', by_alias=True)

    def diagnostic(self):
        start = perf_counter()
        vectors, tokens = self.encoder.encode(['本地语义检索验证', '用不同说法寻找相近资料'])
        return {'dimensions': int(vectors.shape[1]), 'finite': bool(self.encoder.np.isfinite(vectors).all()),
                'tokens': tokens, 'loadSeconds': self.load_seconds, 'inferenceSeconds': perf_counter() - start,
                'peakMemoryBytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}


def main():
    # 平台首版仅 Linux；硬上限涵盖 native runtime 内存，父进程负责超时/取消。
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    engine = None
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if engine is None:
                snapshot = EmbeddingSnapshot.model_validate(message['snapshot'])
                engine = Engine(message['root'], snapshot)
                result = {'ready': True}
            elif message['operation'] == 'diagnostic':
                result = engine.diagnostic()
            elif message['operation'] == 'split':
                result = {'offsets': engine.encoder.split(message['text'])}
            elif message['operation'] == 'split_corpus':
                result = engine.split_corpus(message['request'])
            elif message['operation'] == 'search':
                result = engine.search(message['request'])
            else:
                raise failure('EMBEDDING_INCOMPATIBLE', '未知语义检索操作')
            response = {'value': result}
        except PlatformError as exc:
            response = {'error': exc.error.model_dump(mode='json', by_alias=True)}
        except Exception:
            response = {'error': failure('EMBEDDING_INFERENCE_ERROR', '本地模型工作进程请求或执行失败').error.model_dump(mode='json', by_alias=True)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    main()
