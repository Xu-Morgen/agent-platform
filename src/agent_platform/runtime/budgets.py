"""单任务预算策略；登记与检查在仓储锁内同步完成。"""
from ..contracts.errors import ErrorDetails, ErrorResponse, PlatformError


class LoopPolicy:
    def __init__(self, run_id, snapshot, runs):
        self.run_id, self.runs = run_id, runs
        self.global_limit = snapshot.definition.budget.loop_limit
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
