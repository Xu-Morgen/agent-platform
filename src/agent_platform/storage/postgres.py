"""单后端 PostgreSQL 文档存储；批次事务和会话锁保护实例发布。"""
import json
from threading import RLock
from . import storage_error


class PostgresStore:
    durable = True

    def __init__(self, url):
        self.lock = RLock()
        self.connection = None
        self.failed = False
        try:
            import psycopg
        except ImportError:
            raise storage_error('PostgreSQL 模式需要安装 psycopg[binary]，参见 docs/persistence.md') from None
        try:
            self.connection = psycopg.connect(url, autocommit=True, connect_timeout=5)
            self.connection.execute("SET statement_timeout = '5s'")
            self.connection.execute("SET lock_timeout = '5s'")
            # 锁生命周期等于连接生命周期；断线后禁止透明重连绕过单进程约束。
            owned = self.connection.execute('SELECT pg_try_advisory_lock(716243, 1)').fetchone()[0]
            if not owned:
                raise storage_error('此数据库已有 Agent Platform 后端运行；当前版本只支持单后端')
            with self.connection.transaction():
                self.connection.execute('CREATE TABLE IF NOT EXISTS agent_platform_meta (id integer PRIMARY KEY CHECK (id = 1), version integer NOT NULL)')
                self.connection.execute('INSERT INTO agent_platform_meta VALUES (1, 1) ON CONFLICT DO NOTHING')
                version = self.connection.execute('SELECT version FROM agent_platform_meta WHERE id = 1').fetchone()[0]
                if version != 1:
                    raise storage_error('存储格式版本不兼容，请使用匹配版本的后端')
                self.connection.execute('CREATE TABLE IF NOT EXISTS agent_platform_documents (collection text NOT NULL, key text NOT NULL, document jsonb NOT NULL, PRIMARY KEY (collection, key))')
        except Exception as exc:
            self.close()
            from ..contracts.errors import PlatformError
            if isinstance(exc, PlatformError):
                raise
            raise storage_error('PostgreSQL 初始化失败，请检查连接配置、权限和数据库可用性') from None

    def check(self):
        with self.lock:
            if self.failed:
                raise storage_error()
            try:
                self.connection.execute('SELECT 1')
            except Exception:
                self.failed = True
                raise storage_error() from None

    def read(self, collection):
        with self.lock:
            self.check()
            try:
                rows = self.connection.execute('SELECT key, document FROM agent_platform_documents WHERE collection = %s ORDER BY key', (collection,)).fetchall()
                return dict(rows)
            except Exception:
                self.failed = True
                raise storage_error() from None

    def write(self, documents):
        with self.lock:
            self.check()
            try:
                with self.connection.transaction():
                    for collection, key, document in documents:
                        self.connection.execute('INSERT INTO agent_platform_documents (collection, key, document) VALUES (%s, %s, %s::jsonb) ON CONFLICT (collection, key) DO UPDATE SET document = EXCLUDED.document',
                                                (collection, key, json.dumps(document, allow_nan=False)))
            except Exception:
                self.failed = True
                raise storage_error() from None

    def close(self):
        if self.connection is not None:
            self.connection.close()
