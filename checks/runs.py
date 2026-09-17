from agent_platform.repositories.runs import RunRepository
from agent_platform.contracts.errors import PlatformError
r = RunRepository()
args = dict(service_id='svc', instance_id='ins', version='1.0', revision=1, input={'text': '合成'})
a, b = r.create(**args), r.create(**args)
r.update(a.run_id, status='running')
assert r.get(b.run_id).status == 'queued'
r.finish(a.run_id, 'completed', result={'text': '完成'})
try:
    r.update(a.run_id, status='running')
    raise AssertionError()
except ValueError:
    pass
try:
    r.get('missing')
    raise AssertionError()
except PlatformError as exc:
    assert exc.status_code == 404
assert r.get(a.run_id).result == {'text': '完成'}
print('运行仓储：独立记录、终态保护、404 通过')
