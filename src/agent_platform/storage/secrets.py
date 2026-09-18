"""持久凭据使用外部主密钥加密；密钥不得存入平台数据库。"""
import os
from . import storage_error


def credential_cipher():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise storage_error('持久化凭据需要 cryptography，参见 docs/persistence.md') from None
    key = os.environ.get('AGENT_PLATFORM_CREDENTIAL_KEY')
    if not key:
        raise storage_error('持久化模式必须配置 AGENT_PLATFORM_CREDENTIAL_KEY；主密钥应独立备份')
    try:
        return Fernet(key.encode('ascii'))
    except (ValueError, UnicodeError):
        raise storage_error('AGENT_PLATFORM_CREDENTIAL_KEY 格式无效') from None
