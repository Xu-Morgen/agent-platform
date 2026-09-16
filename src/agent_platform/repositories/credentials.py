"""凭据只驻留内存；公开读取仅返回引用及固定掩码。"""
from uuid import uuid4
from pydantic import SecretStr
from ..contracts.base import StrictModel
from ..contracts.errors import ErrorResponse, PlatformError


class CredentialReference(StrictModel):
    credential_ref: str
    mask: str = '********'


class CredentialRepository:
    def __init__(self):
        self._values: dict[str, SecretStr] = {}

    def put(self, value: SecretStr) -> CredentialReference:
        if not isinstance(value, SecretStr) or not value.get_secret_value().strip():
            raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='credentials',
                                             message='凭据不能为空', field_path=['credential']))
        reference = 'cred_' + uuid4().hex
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
