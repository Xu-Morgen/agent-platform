"""桌面专用 PostgreSQL 生命周期；只管理本应用的数据目录和进程。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile

from . import storage_error


def default_data_directory():
    if sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support'
    elif os.name == 'nt':
        root = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    else:
        root = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return root / 'Agent Platform' / 'storage'


class LocalPostgres:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.data = self.directory / 'postgresql'
        self.log = self.directory / 'postgresql.log'
        self.lock = None
        self.started = False
        self.bin = None
        self.connection_url = None
        self.credential_key = None

    def _acquire(self):
        if os.name != 'posix':
            raise storage_error('当前本地数据库生命周期仅支持 Linux/macOS；Windows 支持尚未交付')
        import fcntl
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = os.fdopen(os.open(self.directory / 'desktop.lock', os.O_CREAT | os.O_RDWR, 0o600), 'a+')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            raise storage_error('此数据目录已有后端运行，请关闭现有应用后再启动') from None

    def _binaries(self):
        required = (self.data / 'PG_VERSION').read_text().strip() if self.data.exists() else None
        explicit = os.environ.get('AGENT_PLATFORM_POSTGRES_BIN')
        private = Path.home() / '.local/share/agent-platform/postgresql/usr/lib/postgresql'
        candidates = [Path(explicit)] if explicit else []
        if not explicit:
            executable = shutil.which('postgres')
            if executable:
                candidates.append(Path(executable).resolve().parent)
            for parent in (private, Path('/usr/lib/postgresql')):
                if parent.exists():
                    candidates.extend(sorted(parent.glob('*/bin'), reverse=True))
            candidates.extend([Path('/opt/homebrew/opt/postgresql@16/bin'), Path('/usr/local/opt/postgresql@16/bin')])
        for directory in candidates:
            if not all((directory / name).is_file() for name in ('postgres', 'initdb', 'pg_ctl')):
                continue
            env = os.environ.copy()
            # Ubuntu 用户级安装保留发行包目录结构；不改系统动态链接配置。
            if len(directory.parents) >= 4:
                libraries = list((directory.parents[3] / 'lib').glob('*-linux-gnu'))
                if libraries:
                    env['LD_LIBRARY_PATH'] = os.pathsep.join([str(p) for p in libraries] + ([env['LD_LIBRARY_PATH']] if env.get('LD_LIBRARY_PATH') else []))
            try:
                result = subprocess.run([str(directory / 'postgres'), '--version'], env=env,
                                        capture_output=True, text=True, timeout=5, check=True)
                major = re.search(r'PostgreSQL\) (\d+)', result.stdout).group(1)
            except (OSError, subprocess.SubprocessError, AttributeError):
                continue
            if required and major != required:
                continue
            self.bin, self.pg_env = directory, env
            return
        reason = f'需要 PostgreSQL {required}，不会自动升级已有数据库' if required else '未找到可用的 PostgreSQL 程序'
        raise storage_error(reason + '；参见 docs/persistence.md 或设置 AGENT_PLATFORM_POSTGRES_BIN')

    def _secrets(self):
        from cryptography.fernet import Fernet
        path = self.directory / 'secrets.json'
        if not path.exists():
            if self.data.exists():
                raise storage_error('本地数据库密钥文件缺失；请恢复原 secrets.json，不会重新生成或清空数据')
            value = {'format': 1, 'password': secrets.token_urlsafe(32),
                     'credentialKey': Fernet.generate_key().decode('ascii')}
            # 原子发布，初始化崩溃不会留下半份密钥文件。
            fd, temporary = tempfile.mkstemp(prefix='.secrets-', dir=self.directory)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(value, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        try:
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise ValueError()
            value = json.loads(path.read_text())
            if value['format'] != 1 or not isinstance(value['password'], str) or len(value['password']) < 32:
                raise ValueError()
            Fernet(value['credentialKey'].encode('ascii'))
        except (ValueError, KeyError, TypeError, OSError):
            raise storage_error('本地密钥文件无效或可被其他用户读取；请检查 secrets.json，原文件不会被覆盖') from None
        self.password, self.credential_key = value['password'], value['credentialKey']

    def _command(self, program, args, *, timeout=40):
        try:
            result = subprocess.run([str(self.bin / program), *args], env=self.pg_env,
                                    capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            raise storage_error(f'本地 PostgreSQL {program} 执行失败，请检查 {self.log}') from None
        if result.returncode:
            with self.log.open('a') as stream:
                stream.write(result.stdout + result.stderr)
            raise storage_error(f'本地 PostgreSQL {program} 失败，请检查 {self.log}')
        return result

    def _initialize(self):
        if self.data.exists():
            if not (self.data / 'PG_VERSION').is_file():
                raise storage_error('数据库目录不完整；请检查或恢复备份，程序不会删除已有目录')
            return
        staging = Path(tempfile.mkdtemp(prefix='.postgresql-init-', dir=self.directory))
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.directory, prefix='.pg-password-') as password:
                password.write(self.password + '\n')
                password.flush()
                args = ['-D', str(staging), '--username=agent_platform', '--encoding=UTF8', '--locale=C',
                        '--auth-local=scram-sha-256', '--auth-host=scram-sha-256', '--pwfile', password.name]
                if len(self.bin.parents) >= 4:
                    share = self.bin.parents[3] / 'share/postgresql' / self.bin.parent.name
                    if share.is_dir():
                        args += ['-L', str(share)]
                self._command('initdb', args)
            staging.rename(self.data)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def _running(self):
        result = subprocess.run([str(self.bin / 'pg_ctl'), '-D', str(self.data), 'status'],
                                env=self.pg_env, capture_output=True, timeout=5)
        if result.returncode not in (0, 3):
            raise storage_error('无法确认本地数据库运行状态，不会删除数据库锁文件')
        return result.returncode == 0

    def _stop_database(self):
        if self._running():
            self._command('pg_ctl', ['-D', str(self.data), '-m', 'fast', '-w', '-t', '10', 'stop'], timeout=15)

    def __enter__(self):
        try:
            self._acquire()
            if self.data.exists() and not (self.data / 'PG_VERSION').is_file():
                raise storage_error('数据库目录不完整；不会覆盖已有数据')
            self._binaries()
            self._secrets()
            fd = os.open(self.log, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            os.close(fd)
            self._initialize()
            # 已取得目录独占锁，残留数据库只能属于上次退出的本应用实例。
            self._stop_database()
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            options = f"-h 127.0.0.1 -p {port} -c unix_socket_directories='' -c max_connections=20 -c shared_buffers=32MB -c jit=off"
            self.started = True
            self._command('pg_ctl', ['-D', str(self.data), '-l', str(self.log), '-w', '-t', '20',
                                     '-o', options, 'start'], timeout=25)
            import psycopg
            from psycopg.conninfo import make_conninfo
            self.connection_url = make_conninfo(host='127.0.0.1', port=port, dbname='postgres',
                                               user='agent_platform', password=self.password)
            try:
                with psycopg.connect(self.connection_url, autocommit=True, connect_timeout=5) as connection:
                    if not connection.execute("SELECT 1 FROM pg_database WHERE datname = 'agent_platform'").fetchone():
                        connection.execute('CREATE DATABASE agent_platform')
            except psycopg.Error:
                raise storage_error('本地数据库认证或初始化失败，请检查日志；不会覆盖密钥') from None
            self.connection_url = make_conninfo(self.connection_url, dbname='agent_platform')
            return self
        except BaseException:
            self.close()
            raise

    @contextmanager
    def environment(self):
        settings = {'AGENT_PLATFORM_DATABASE_URL': self.connection_url,
                    'AGENT_PLATFORM_CREDENTIAL_KEY': self.credential_key,
                    'AGENT_PLATFORM_DATA_DIR': str(self.directory)}
        previous = {name: os.environ.get(name) for name in settings}
        os.environ.update(settings)
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def close(self):
        try:
            if self.started:
                self._stop_database()
                self.started = False
        finally:
            if self.lock is not None:
                self.lock.close()
                self.lock = None

    def __exit__(self, *_):
        self.close()
