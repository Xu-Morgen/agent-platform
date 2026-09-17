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
