"""单任务预算策略；登记与检查在仓储锁内同步完成。"""
from ..contracts.errors import ErrorDetails, ErrorResponse, PlatformError


class LoopPolicy:
    def __init__(self, run_id, snapshot, runs):
        self.run_id, self.runs = run_id, runs
        self.global_limit = snapshot.draft.budget.loop_limit
        self.local_limits = {
            key: snapshot.draft.node_configurations[key].budget.loop_limit
            for key in snapshot.packages
        }

    def __call__(self, phase, binding_id):
        if phase != 'package_start':
            return
        with self.runs.lock:
            usage = self.runs.get(self.run_id).usage
            ledger = usage.setdefault('loops', {'global': 0, 'bindings': {}})
            used = ledger['bindings'].get(binding_id, 0)
            if used >= self.local_limits[binding_id] or ledger['global'] >= self.global_limit:
                raise PlatformError(ErrorResponse(
                    code='LOOP_BUDGET_EXCEEDED', stage='budget.loop',
                    message='包调用次数额度不足', run_id=self.run_id,
                    details=ErrorDetails(package_binding_id=binding_id, attempt=used + 1)))
            ledger['bindings'][binding_id] = used + 1
            ledger['global'] += 1
            self.runs.update(self.run_id, usage=usage)


class TokenLedger:
    """每个模型请求记录供应商实际用量，缺失时明确标记未知。"""
    def __init__(self, run_id, runs):
        self.run_id, self.runs = run_id, runs
        self.entries = {}

    def settle(self, request_id, binding_id, usage):
        with self.runs.lock:
            if request_id in self.entries:
                raise ValueError('模型请求重复核销')
            self.entries[request_id] = (binding_id, usage.model_copy(deep=True))
            self.publish()

    def summary(self, binding_id=None):
        entries = [u for b, u in self.entries.values() if binding_id is None or b == binding_id]
        unknown = any(u.quality == 'unsupported' for u in entries)
        known_input = sum(u.input_tokens or 0 for u in entries)
        known_output = sum(u.output_tokens or 0 for u in entries)
        quality = 'unsupported' if unknown else 'exact'
        return {'inputTokens': None if unknown else known_input,
                'outputTokens': None if unknown else known_output,
                'totalTokens': None if unknown else known_input + known_output,
                'knownTokens': known_input + known_output,
                'quality': quality, 'sources': sorted({u.source for u in entries})}

    def publish(self):
        bindings = {b for b, _ in self.entries.values()}
        usage = self.runs.get(self.run_id).usage
        usage['tokens'] = {'global': self.summary(),
                           'bindings': {b: self.summary(b) for b in sorted(bindings)}}
        self.runs.update(self.run_id, usage=usage)


class TokenPolicy:
    def __init__(self, run_id, snapshot, runs):
        self.ledger = TokenLedger(run_id, runs)
        self.global_limit = snapshot.draft.budget.token_limit
        self.local_limits = {b: snapshot.draft.node_configurations[b].budget.token_limit for b in snapshot.packages}

    def error(self, code, message):
        return PlatformError(ErrorResponse(code=code, stage='budget.token', message=message,
                                          run_id=self.ledger.run_id))

    def remaining(self, binding_id):
        global_usage, local = self.ledger.summary(), self.ledger.summary(binding_id)
        if global_usage['totalTokens'] is None:
            raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '模型用量未知')
        return min(self.global_limit - global_usage['totalTokens'],
                   self.local_limits[binding_id] - local['totalTokens'])

    def __call__(self, phase, step_id):
        if phase == 'cleanup':
            return
        summaries = [(self.ledger.summary(), self.global_limit)]
        summaries += [(self.ledger.summary(b), limit) for b, limit in self.local_limits.items()]
        for usage, limit in summaries:
            if usage['totalTokens'] is None:
                raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '缺少可用模型计量')
            if usage['totalTokens'] > limit:
                raise self.error('TOKEN_BUDGET_EXCEEDED', '累计 token 用量超过限额')

    async def invoke(self, binding_id, adapter, connection, request):
        from uuid import uuid4
        from ..contracts.models import ModelUsage
        self('model_start', binding_id)
        remaining = self.remaining(binding_id)
        if remaining <= 0:
            raise self.error('TOKEN_BUDGET_EXCEEDED', '没有后续模型调用额度')
        limited = request.model_copy(update={'max_output_tokens': min(request.max_output_tokens, remaining)})
        request_id = uuid4().hex
        try:
            response = await adapter.invoke(connection, limited)
        except Exception as exc:
            usage = getattr(exc, 'usage', None)
            if usage is None:
                usage = ModelUsage(quality='unsupported', source='model:failed_without_usage')
            self.ledger.settle(request_id, binding_id, usage)
            exc.usage = usage
            raise
        usage = response.usage
        self.ledger.settle(request_id, binding_id, usage)
        if usage.quality == 'unsupported':
            raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '模型未返回 usage')
        # 超额在紧随响应的统一状态检查处失败，不发布成功结果。
        return response
