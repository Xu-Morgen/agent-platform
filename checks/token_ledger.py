from agent_platform.repositories.runs import RunRepository
from agent_platform.contracts.models import ModelUsage
from agent_platform.runtime.budgets import TokenLedger

runs = RunRepository()
run = runs.create(service_id='s', instance_id='i', version='1.0', revision=1, input={})
ledger = TokenLedger(run.run_id, runs)
ledger.reserve('one', 'a', 20, 30)
assert ledger.summary()['totalTokens'] == 0 and ledger.summary()['reservedTokens'] == 50
ledger.settle('one', 'a', ModelUsage(input_tokens=10, output_tokens=5, quality='exact', source='provider'))
ledger.settle('two', 'b', ModelUsage(input_tokens=4, output_tokens=3, quality='estimated', source='synthetic-estimator'))
assert ledger.summary()['totalTokens'] == 22 and ledger.summary()['reservedTokens'] == 0
assert ledger.summary('a')['totalTokens'] == 15 and ledger.summary('b')['totalTokens'] == 7
assert ledger.summary()['quality'] == 'estimated'
try:
    ledger.settle('one', 'a', ModelUsage(quality='unsupported', source='missing'))
except ValueError:
    pass
else:
    raise AssertionError('重复核销未拒绝')
ledger.settle('three', 'a', ModelUsage(quality='unsupported', source='missing'))
assert ledger.summary()['totalTokens'] is None and ledger.summary()['knownTokens'] == 22
assert runs.get(run.run_id).usage['tokens']['global']['quality'] == 'unsupported'
print('PASS: 双请求累计 22；局部独立；预留释放不重复；未知非精确零；来源保留')
