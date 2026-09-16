from pydantic import SecretStr
from agent_platform.repositories.credentials import CredentialRepository
from agent_platform.contracts.errors import PlatformError

repo = CredentialRepository()
secret = 'synthetic-credential-i2'
ref = repo.put(SecretStr(secret))
assert secret not in ref.model_dump_json()
assert secret not in repr(repo._values)
assert repo.get(ref.credential_ref).mask == '********'
assert repo.resolve_for_transport(ref.credential_ref).get_secret_value() == secret
for fresh in (CredentialRepository(), repo):
    fresh.clear()
    try:
        fresh.get(ref.credential_ref)
    except PlatformError as exc:
        assert secret not in str(exc) and exc.status_code == 404
    else:
        raise AssertionError('credential survived session cleanup')
print('I2-T01 PASS: masked reads, redacted representation, session isolation')
