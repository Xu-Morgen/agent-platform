import asyncio
from strict_tokens import policy, SyntheticAdapter
from agent_platform.runtime.budgets import NonStrictTokenPolicy
from agent_platform.contracts.models import ModelRequest, ModelResponse, ModelUsage
from agent_platform.contracts.errors import PlatformError

class Adapter(SyntheticAdapter):
    usage = ModelUsage(input_tokens=7, output_tokens=4, quality='exact', source='synthetic')
    async def invoke(self, connection, request):
        self.calls += 1
        return ModelResponse(output={}, usage=self.usage)

async def main():
    req = ModelRequest(messages=[{'role':'user','content':'合成'}], max_output_tokens=20)
    a = Adapter()
    p = policy(10)
    p.__class__ = NonStrictTokenPolicy
    await p.invoke('a', a, None, req)
    try:
        p('terminal', 'report')
    except PlatformError as exc:
        assert exc.error.code == 'TOKEN_BUDGET_EXCEEDED'
    else:
        raise AssertionError()
    p('cleanup', 'report')
    p = policy(11)
    p.__class__ = NonStrictTokenPolicy
    await p.invoke('a', a, None, req)
    p('terminal', 'report')
    before = a.calls
    try:
        await p.invoke('a', a, None, req)
    except PlatformError as exc:
        assert exc.error.code == 'TOKEN_BUDGET_EXCEEDED' and a.calls == before
    else:
        raise AssertionError()
    a.usage = ModelUsage(quality='unsupported', source='missing')
    p = policy(11)
    p.__class__ = NonStrictTokenPolicy
    try:
        await p.invoke('a', a, None, req)
    except PlatformError as exc:
        assert exc.error.code == 'TOKEN_ACCOUNTING_UNSUPPORTED' and p.ledger.summary()['totalTokens'] is None
    else:
        raise AssertionError()
    async def estimate(*args):
        return ModelUsage(input_tokens=4, output_tokens=2, quality='estimated', source='synthetic:estimator')
    a.estimate_usage = estimate
    p = policy(11)
    p.__class__ = NonStrictTokenPolicy
    await p.invoke('a', a, None, req)
    assert p.ledger.summary()['quality'] == 'estimated'
    print('PASS: 响应超额下一流转失败；满额允许终态而拒绝新请求；未知明确失败；估算标注来源')

asyncio.run(main())
