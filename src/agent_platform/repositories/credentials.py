"""公开读取仅返回引用；持久化模式只写加密凭据。"""
from uuid import uuid4
from pydantic import SecretStr
from ..contracts.base import StrictModel
from ..contracts.errors import ErrorResponse, PlatformError


class CredentialReference(StrictModel):
    credential_ref: str
    mask: str = '********'


class CredentialRepository:
    def __init__(self, store=None):
        from ..storage import MemoryStore, storage_error
        from ..storage.secrets import credential_cipher
        self.store = store or MemoryStore()
        self.cipher = credential_cipher() if self.store.durable else None
        self._values: dict[str, SecretStr] = {}
        for reference, document in self.store.read('credentials').items():
            try:
                self._values[reference] = SecretStr(self.cipher.decrypt(document['ciphertext'].encode()).decode())
            except Exception:
                raise storage_error('凭据无法解密；请恢复原主密钥，不会清空或覆盖已有凭据') from None

    def put(self, value: SecretStr) -> CredentialReference:
        if not isinstance(value, SecretStr) or not value.get_secret_value().strip():
            raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='credentials',
                                             message='凭据不能为空', field_path=['credential']))
        reference = 'cred_' + uuid4().hex
        if self.cipher:
            self.store.write([('credentials', reference, {
                'ciphertext': self.cipher.encrypt(value.get_secret_value().encode()).decode(),
            })])
        self._values[reference] = value
        return self.get(reference)

    def get(self, reference: str) -> CredentialReference:
        if reference not in self._values:
            raise PlatformError(ErrorResponse(code='RECORD_NOT_FOUND', stage='credentials',
                                             message='凭据引用不存在'), 404)
        return CredentialReference(credential_ref=reference)

    def resolve_for_transport(self, reference: str) -> SecretStr:
        """仅供后续传输适配器使用，不接入公开 API 或日志。"""
        self.get(reference)
        return self._values[reference]

    def clear(self) -> None:
        self._values.clear()
