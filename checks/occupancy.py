from agent_platform.repositories.environments import EnvironmentRepository
from agent_platform.repositories.credentials import CredentialRepository
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.errors import PlatformError
r = EnvironmentRepository(CredentialRepository())
w = EnvironmentWrite(name='合成', connections=[{'connectionId':'api', 'kind':'api', 'baseUrl':'http://localhost'}])
a, b = r.save(w), r.save(w)
r.occupy([a.environment_id], 'run_manual')
try:
    r.save(w, a.environment_id)
    raise AssertionError()
except PlatformError as exc:
    assert exc.status_code == 409 and exc.error.details.active_run_ids == ['run_manual']
assert r.save(w, b.environment_id).revision == 2
r.release('run_manual')
assert r.save(w, a.environment_id).revision == 2
print('人工 runId 占用 A 拒绝更新，B 成功；释放 A 后更新成功')
