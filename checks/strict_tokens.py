"""严格能力由显式合成适配器提供；Ollama 本身不声明严格支持。"""
import asyncio
from types import SimpleNamespace
from agent_platform.contracts.models import ModelRequest, ModelResponse, ModelUsage
from agent_platform.contracts.errors import PlatformError, upstream_error
from agent_platform.adapters.model_protocol import OLLAMA_CAPABILITIES
from agent_platform.runtime.budgets import StrictTokenPolicy
from agent_platform.repositories.runs import RunRepository

class SyntheticAdapter:
    capabilities = OLLAMA_CAPABILITIES.model_copy(update={
        'strict_total_limit': True, 'hidden_tokens_verified': True, 'input_preflight': 'upper_bound'})
    calls = 0
    fail = False
    async def preflight(self, connection, request):
        return ModelUsage(input_tokens=6, output_tokens=0, quality='upper_bound', source='synthetic')
    async def invoke(self, connection, request):
        self.calls += 1
        self.limit = request.max_output_tokens
        if self.fail:
            raise upstream_error('model', timeout=True)
        return ModelResponse(output={}, usage=ModelUsage(input_tokens=4, output_tokens=2, quality='exact', source='synthetic'))

def policy(limit):
    runs = RunRepository()
    run = runs.create(service_id='s', instance_id='i', version='1.0', revision=1, input={})
    snapshot = SimpleNamespace(definition=SimpleNamespace(budget=SimpleNamespace(token_limit=limit)),
                               configuration={'packages.a': {'tokenLimit': limit}}, packages={'a': None})
    return StrictTokenPolicy(run.run_id, snapshot, runs)

async def main():
    req = ModelRequest(messages=[{'role':'user', 'content':'合成'}], max_output_tokens=20)
    adapter = SyntheticAdapter()
    try:
        await policy(6).invoke('a', adapter, None, req)
    except PlatformError as exc:
        assert exc.error.code == 'TOKEN_BUDGET_EXCEEDED' and adapter.calls == 0
    else:
        raise AssertionError()
    p = policy(10)
    await p.invoke('a', adapter, None, req)
    assert adapter.limit == 4 and p.remaining('a') == 4
    assert p.ledger.summary()['reservedTokens'] == 0
    adapter.fail = True
    p = policy(40)
    try:
        await p.invoke('a', adapter, None, req)
    except PlatformError as exc:
        assert exc.error.code == 'MODEL_TIMEOUT'
        assert p.remaining('a') == 14 and p.ledger.summary()['totalTokens'] == 26
        assert p.ledger.summary()['quality'] == 'upper_bound' and p.ledger.summary()['reservedTokens'] == 0
    else:
        raise AssertionError()
    adapter.capabilities = OLLAMA_CAPABILITIES
    before = adapter.calls
    try:
        await policy(40).invoke('a', adapter, None, req)
    except PlatformError as exc:
        assert exc.error.code == 'TOKEN_ACCOUNTING_UNSUPPORTED' and adapter.calls == before
    else:
        raise AssertionError()
    print('PASS: 不足额零请求；输出按剩余量收缩；实际核销；超时保留请求上界并释放占用；不支持不降级')

if __name__ == '__main__':
    asyncio.run(main())
