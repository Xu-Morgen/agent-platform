"""单任务预算策略；登记与检查在仓储锁内同步完成。"""
from ..contracts.errors import ErrorDetails, ErrorResponse, PlatformError


class LoopPolicy:
    def __init__(self, run_id, snapshot, runs):
        self.run_id, self.runs = run_id, runs
        self.global_limit = snapshot.draft.budget.loop_limit
        self.local_limits = {
            key: snapshot.configuration['packages.' + key]['loopLimit']
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
    """每个模型请求单独核销；预留仅占额度，不计入已用量。"""
    def __init__(self, run_id, runs):
        self.run_id, self.runs = run_id, runs
        self.entries = {}
        self.reservations = {}

    def reserve(self, request_id, binding_id, input_tokens, output_tokens):
        with self.runs.lock:
            if request_id in self.entries or request_id in self.reservations:
                raise ValueError('模型请求重复登记')
            if min(input_tokens, output_tokens) < 0:
                raise ValueError('预留不可为负数')
            self.reservations[request_id] = (binding_id, input_tokens, output_tokens)
            self.publish()

    def settle(self, request_id, binding_id, usage):
        with self.runs.lock:
            if request_id in self.entries:
                raise ValueError('模型请求重复核销')
            reserved = self.reservations.get(request_id)
            if reserved and reserved[0] != binding_id:
                raise ValueError('模型请求绑定不一致')
            self.entries[request_id] = (binding_id, usage.model_copy(deep=True))
            self.reservations.pop(request_id, None)
            self.publish()

    def summary(self, binding_id=None):
        entries = [u for b, u in self.entries.values() if binding_id is None or b == binding_id]
        reserved = sum(i + o for b, i, o in self.reservations.values() if binding_id is None or b == binding_id)
        unknown = any(u.quality == 'unsupported' for u in entries)
        known_input = sum(u.input_tokens or 0 for u in entries)
        known_output = sum(u.output_tokens or 0 for u in entries)
        qualities = {u.quality for u in entries}
        quality = next((q for q in ('unsupported', 'estimated', 'upper_bound', 'exact') if q in qualities), 'exact')
        return {'inputTokens': None if unknown else known_input,
                'outputTokens': None if unknown else known_output,
                'totalTokens': None if unknown else known_input + known_output,
                'knownTokens': known_input + known_output, 'reservedTokens': reserved,
                'quality': quality, 'sources': sorted({u.source for u in entries})}

    def publish(self):
        bindings = {b for b, _ in self.entries.values()} | {b for b, _, _ in self.reservations.values()}
        usage = self.runs.get(self.run_id).usage
        usage['tokens'] = {'global': self.summary(),
                           'bindings': {b: self.summary(b) for b in sorted(bindings)}}
        self.runs.update(self.run_id, usage=usage)


class StrictTokenPolicy:
    def __init__(self, run_id, snapshot, runs):
        self.ledger = TokenLedger(run_id, runs)
        self.global_limit = snapshot.draft.budget.token_limit
        self.local_limits = {b: snapshot.configuration['packages.' + b]['tokenLimit'] for b in snapshot.packages}

    def error(self, code, message):
        return PlatformError(ErrorResponse(code=code, stage='budget.token', message=message,
                                          run_id=self.ledger.run_id))

    def remaining(self, binding_id):
        global_usage, local = self.ledger.summary(), self.ledger.summary(binding_id)
        if global_usage['totalTokens'] is None:
            raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '模型用量未知')
        return min(self.global_limit - global_usage['totalTokens'] - global_usage['reservedTokens'],
                   self.local_limits[binding_id] - local['totalTokens'] - local['reservedTokens'])

    def __call__(self, phase, step_id):
        if phase == 'cleanup':
            return
        summaries = [(self.ledger.summary(), self.global_limit)]
        summaries += [(self.ledger.summary(b), limit) for b, limit in self.local_limits.items()]
        for usage, limit in summaries:
            if usage['totalTokens'] is None:
                raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '缺少可用模型计量或明确来源的估算')
            if usage['totalTokens'] > limit:
                raise self.error('TOKEN_BUDGET_EXCEEDED', '累计 token 用量超过限额')

    async def invoke(self, binding_id, adapter, connection, request):
        from uuid import uuid4
        from ..contracts.models import ModelUsage
        caps = adapter.capabilities
        if not (caps.strict_total_limit and caps.hidden_tokens_verified and caps.output_limit
                and caps.input_preflight in ('exact', 'upper_bound')
                and caps.response_usage in ('exact', 'upper_bound')):
            raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '适配器不能保证严格 token 上限')
        preflight = await adapter.preflight(connection, request)
        if preflight.quality not in ('exact', 'upper_bound') or preflight.output_tokens != 0:
            raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '缺少完整输入计量或可靠上界')
        with self.ledger.runs.lock:
            output_limit = min(request.max_output_tokens, self.remaining(binding_id) - preflight.input_tokens)
            if output_limit <= 0:
                raise self.error('TOKEN_BUDGET_EXCEEDED', '剩余额度不足以发送模型请求')
            request_id = uuid4().hex
            self.ledger.reserve(request_id, binding_id, preflight.input_tokens, output_limit)
        upper = ModelUsage(input_tokens=preflight.input_tokens, output_tokens=output_limit,
                           quality='upper_bound', source='strict:reserved_upper_bound')
        limited = request.model_copy(update={'max_output_tokens': output_limit})
        try:
            response = await adapter.invoke(connection, limited)
        except Exception as exc:
            usage = getattr(exc, 'usage', None)
            if usage is None or usage.quality not in ('exact', 'upper_bound'):
                usage = upper
            self.ledger.settle(request_id, binding_id, usage)
            # 原始超时/传输错误优先，仍把核销的上界传给步骤记录。
            exc.usage = usage
            raise
        usage = response.usage
        if usage.quality not in ('exact', 'upper_bound'):
            self.ledger.settle(request_id, binding_id, upper)
            raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '严格请求返回未知或不可靠用量')
        self.ledger.settle(request_id, binding_id, usage)
        if usage.input_tokens > preflight.input_tokens or usage.output_tokens > output_limit:
            raise self.error('TOKEN_BUDGET_EXCEEDED', '供应商用量违反预留上界')
        return response


class NonStrictTokenPolicy(StrictTokenPolicy):
    async def invoke(self, binding_id, adapter, connection, request):
        from uuid import uuid4
        from ..contracts.models import ModelUsage
        self('model_start', binding_id)
        remaining = self.remaining(binding_id)
        if remaining <= 0:
            raise self.error('TOKEN_BUDGET_EXCEEDED', '没有后续模型调用额度')
        preflight = await adapter.preflight(connection, request)
        if preflight.quality != 'unsupported':
            remaining -= preflight.input_tokens
        if remaining <= 0:
            raise self.error('TOKEN_BUDGET_EXCEEDED', '输入已耗尽剩余额度')
        limited = request
        if adapter.capabilities.output_limit:
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
        if usage.quality == 'unsupported' and hasattr(adapter, 'estimate_usage'):
            usage = await adapter.estimate_usage(connection, limited, response)
            if usage.quality != 'estimated':
                raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '估算接口必须标明 estimated 及来源')
            response = response.model_copy(update={'usage': usage})
        self.ledger.settle(request_id, binding_id, usage)
        if usage.quality == 'unsupported':
            raise self.error('TOKEN_ACCOUNTING_UNSUPPORTED', '模型无 usage 且无法估算')
        # 超额在紧随响应的统一状态检查处失败，不发布成功结果。
        return response
