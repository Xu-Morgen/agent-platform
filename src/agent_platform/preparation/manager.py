"""wheel-only 环境锁定、摘要缓存、原子发布及可取消准备。"""
import errno
import fcntl
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit, unquote
import httpx
from packaging.utils import canonicalize_name
from ..contracts.errors import ErrorResponse, PlatformError


def failed(code, message):
    return PlatformError(ErrorResponse(code=code, stage='preparation', message=message), 422)


def digest_file(path):
    digest = sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Preparation:
    def __init__(self, *, cancel=None, progress=None, timeout=600):
        self.cancel = cancel or threading.Event()
        self.progress = progress or (lambda event: None)
        self.deadline = time.monotonic() + timeout

    def check(self):
        if self.cancel.is_set():
            raise failed('PREPARATION_CANCELLED', '已取消环境准备')
        if time.monotonic() >= self.deadline:
            raise failed('PREPARATION_TIMEOUT', '环境准备超过整体超时')

    def report(self, phase, **values):
        self.check()
        self.progress({'phase': phase, **values})

    def command(self, command, *, env=None):
        self.check()
        # 不经 shell；使用临时输出文件避免子进程管道填满。
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, env=env)
            try:
                while process.poll() is None:
                    self.check()
                    self.cancel.wait(.1)
                output.seek(0)
                detail = output.read().decode(errors='replace')
                if process.returncode:
                    code = ('PREPARATION_DISK_FULL' if 'No space left' in detail else
                            'DEPENDENCY_CONFLICT' if 'ResolutionImpossible' in detail else
                            'DEPENDENCY_WHEEL_UNAVAILABLE' if 'No matching distribution' in detail else
                            'PREPARATION_NETWORK_ERROR' if any(t in detail for t in ('ConnectionError', 'Connection broken', 'Retrying', 'Timeout')) else 'DEPENDENCY_ERROR')
                    raise failed(code, '依赖解析或安装失败；仅支持当前 Python/架构的 wheel，请检查版本约束、软件源及系统库')
                return detail
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


class RuntimeManager:
    def __init__(self, root=None):
        from ..storage.local import default_data_directory
        self.root = Path(root or os.environ.get('AGENT_PLATFORM_RUNTIME_DIR') or Path(os.environ.get('AGENT_PLATFORM_DATA_DIR', default_data_directory())) / 'runtimes')
        self.root.mkdir(parents=True, exist_ok=True)
        self.runtime = {'python': platform.python_version(), 'implementation': platform.python_implementation(),
                        'platform': sys.platform, 'machine': platform.machine(),
                        'sdk': version('agent-platform'), 'pydantic': version('pydantic'), 'packaging': version('packaging')}
        sdk_root = Path(__file__).resolve().parents[1]
        self.sdk_files = {str(p.relative_to(sdk_root)): p.read_bytes() for p in sorted(sdk_root.rglob('*.py'))}
        self.runtime['sdkDigest'] = fingerprint({name: sha256(content).hexdigest() for name, content in self.sdk_files.items()})

    @contextmanager
    def mutex(self, key, operation):
        with (self.root / (key + '.lock')).open('a') as lock:
            while True:
                operation.check()
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    operation.cancel.wait(.1)
            try: yield
            finally: fcntl.flock(lock, fcntl.LOCK_UN)

    def download(self, url, digest, operation, *, filename=None):
        path = self.root / 'blobs' / digest
        path.parent.mkdir(exist_ok=True)
        with self.mutex('blob-' + digest, operation):
            if path.is_file() and digest_file(path) == digest:
                return path
            operation.report('download', source=url, downloadedBytes=0, totalBytes=None)
            fd, name = tempfile.mkstemp(prefix=digest + '.', suffix='.part', dir=path.parent)
            temporary = Path(name)
            try:
                with os.fdopen(fd, 'wb') as destination, httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=True) as client:
                    with client.stream('GET', url) as response:
                        if response.status_code >= 400:
                            raise failed('PREPARATION_URL_ERROR', f'下载地址不可用（HTTP {response.status_code}）')
                        if any(item.url.scheme != 'https' for item in [*response.history, response]):
                            raise failed('PREPARATION_URL_ERROR', '下载重定向不允许降级到非 HTTPS 地址')
                        total = response.headers.get('content-length')
                        total = int(total) if total and total.isdecimal() else None
                        current, actual = 0, sha256()
                        for chunk in response.iter_bytes(1024 * 256):
                            operation.check()
                            destination.write(chunk)
                            actual.update(chunk)
                            current += len(chunk)
                            operation.report('download', source=url, downloadedBytes=current, totalBytes=total)
                        if actual.hexdigest() != digest:
                            raise failed('PREPARATION_HASH_MISMATCH', '下载文件 SHA-256 与声明不一致')
                    destination.flush()
                    os.fsync(destination.fileno())
                os.replace(temporary, path)
                return path
            except httpx.TimeoutException:
                raise failed('PREPARATION_TIMEOUT', '连接或下载超时') from None
            except httpx.HTTPError:
                raise failed('PREPARATION_NETWORK_ERROR', '下载网络异常；请检查连接后重试，离线执行需要完整缓存') from None
            except OSError as exc:
                raise failed('PREPARATION_DISK_FULL' if exc.errno == errno.ENOSPC else 'DEPENDENCY_ERROR', '磁盘空间不足' if exc.errno == errno.ENOSPC else '缓存文件写入失败') from None
            finally:
                temporary.unlink(missing_ok=True)

    def prepare(self, metadata, *, locked=None, operation=None):
        try:
            return self._prepare(metadata, locked=locked, operation=operation)
        except OSError as exc:
            raise failed('PREPARATION_DISK_FULL' if exc.errno == errno.ENOSPC else 'DEPENDENCY_ERROR',
                         '磁盘空间不足' if exc.errno == errno.ENOSPC else '运行环境缓存无法读写') from None

    def _prepare(self, metadata, *, locked=None, operation=None):
        operation = operation or Preparation()
        operation.report('check')
        declaration = metadata.model_dump(mode='json', by_alias=True, include={'dependencies', 'dependency_sources', 'models'})
        key = fingerprint({'runtime': self.runtime, 'declaration': declaration})
        with self.mutex(key, operation):
            lock_path = self.root / (key + '.json')
            lock = locked or (json.loads(lock_path.read_text()) if lock_path.exists() else None)
            compatibility = ('python', 'implementation', 'platform', 'machine')
            if lock and (any(lock['runtime'][k] != self.runtime[k] for k in compatibility) or lock['declaration'] != declaration):
                raise failed('DEPENDENCY_ERROR', '已锁定运行环境与当前 Python/SDK 不匹配，不自动升级历史实例')
            if lock is None:
                lock = self.resolve(metadata, declaration, operation)
                temporary = lock_path.with_suffix('.part')
                temporary.write_text(json.dumps(lock, sort_keys=True))
                os.replace(temporary, lock_path)
            env_key = fingerprint(lock)
            sdk = self.root / 'sdks' / lock['runtime']['sdkDigest']
            with self.mutex('sdk-' + lock['runtime']['sdkDigest'], operation):
                if not (sdk / 'ready').exists():
                    if lock['runtime']['sdkDigest'] != self.runtime['sdkDigest']:
                        raise failed('DEPENDENCY_ERROR', '历史实例引用的 SDK 缓存缺失，需要恢复对应平台版本')
                    sdk.mkdir(parents=True, exist_ok=True)
                    for name, content in self.sdk_files.items():
                        target = sdk / 'agent_platform' / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content)
                    (sdk / 'ready').write_text(lock['runtime']['sdkDigest'])
            python = self.install(lock, env_key, operation)
            models = {}
            for model in metadata.models:
                blob = self.download(model.url, model.sha256, operation)
                target = self.root / 'models' / model.sha256 / model.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.is_file() or digest_file(target) != model.sha256:
                    temporary = target.with_suffix(target.suffix + '.part')
                    shutil.copyfile(blob, temporary)
                    os.replace(temporary, target)
                models[model.name] = str(target)
            operation.report('verify')
            operation.report('ready')
            return {'lock': lock, 'key': env_key, 'python': str(python), 'models': models, 'sdkPath': str(sdk)}

    def resolve(self, metadata, declaration, operation):
        # 无额外依赖的块使用平台 SDK Python 子进程；声明依赖后才创建独立 venv。
        if not metadata.dependencies:
            return {'runtime': self.runtime, 'declaration': declaration, 'wheels': []}
        operation.report('check', message='锁定直接及传递依赖')
        with tempfile.TemporaryDirectory(prefix='resolve-', dir=self.root) as root:
            python = self.create_environment(Path(root) / 'venv', operation)
            report = Path(root) / 'report.json'
            requirements = list(metadata.dependencies) + [f'pydantic=={version("pydantic")}', f'packaging=={version("packaging")}']
            index = next((s.url for s in metadata.dependency_sources if s.kind == 'index'), 'https://pypi.org/simple')
            wheels = {canonicalize_name(s.package): s for s in metadata.dependency_sources if s.kind == 'wheel'}
            from packaging.requirements import Requirement
            for i, raw in enumerate(requirements):
                req = Requirement(raw)
                if canonicalize_name(req.name) in wheels and (not req.marker or req.marker.evaluate()):
                    source = wheels[canonicalize_name(req.name)]
                    blob = self.download(source.url, source.sha256, operation)
                    filename = unquote(urlsplit(source.url).path).split('/')[-1]
                    local = Path(root) / filename
                    shutil.copyfile(blob, local)
                    requirements[i] = str(local) + ('[' + ','.join(sorted(req.extras)) + ']' if req.extras else '')
            self.pip(python, ['install', '--dry-run', '--ignore-installed', '--only-binary=:all:', '--report', str(report), '--index-url', index, *requirements], operation)
            locked = []
            for item in json.loads(report.read_text())['install']:
                info, package = item['download_info'], item['metadata']
                digest = info.get('archive_info', {}).get('hashes', {}).get('sha256')
                name = canonicalize_name(package['name'])
                source = wheels.get(name)
                url = source.url if source else info['url']
                from ..contracts.dependencies import public_https
                try:
                    public_https(url)
                except ValueError:
                    raise failed('PREPARATION_URL_ERROR', '依赖解析得到不受支持的制品地址，需要无凭据的固定 HTTPS URL') from None
                if not digest or not urlsplit(url).path.endswith('.whl') or urlsplit(url).scheme != 'https':
                    raise failed('DEPENDENCY_WHEEL_UNAVAILABLE', '依赖必须提供可校验摘要的 HTTPS wheel 制品')
                if source and source.sha256 != digest:
                    raise failed('PREPARATION_HASH_MISMATCH', 'wheel 制品与声明摘要不一致')
                for raw in metadata.dependencies:
                    req = Requirement(raw)
                    if (not req.marker or req.marker.evaluate()) and canonicalize_name(req.name) == name and package['version'] not in req.specifier:
                        raise failed('DEPENDENCY_CONFLICT', '指定 wheel 版本与依赖声明不一致')
                locked.append({'name': name, 'version': package['version'], 'url': url, 'sha256': digest,
                               'filename': unquote(urlsplit(url).path).split('/')[-1], 'index': index})
            return {'runtime': self.runtime, 'declaration': declaration, 'wheels': sorted(locked, key=lambda item: item['name'])}

    def create_environment(self, path, operation):
        operation.report('install', message='创建独立 Python 环境')
        import importlib.util
        if importlib.util.find_spec('ensurepip'):
            operation.command([sys.executable, '-m', 'venv', str(path)])
        elif shutil.which('uv'):
            env = {k: v for k, v in os.environ.items() if not k.startswith(('UV_', 'PIP_', 'PYTHON'))}
            operation.command([shutil.which('uv'), '--no-config', 'venv', '--no-project', '--seed',
                '--no-python-downloads', '--python', sys.executable, '--default-index', 'https://pypi.org/simple',
                '--cache-dir', str(self.root / 'bootstrap-cache'), str(path)], env=env)
        else:
            raise failed('DEPENDENCY_ERROR', '创建独立环境需要 Python ensurepip 或已安装的 uv；平台不会修改系统组件')
        return path / 'bin' / 'python'

    def pip(self, python, args, operation):
        # 忽略用户 pip 配置与额外软件源；不接受安装脚本或源码构建。
        env = {k: v for k, v in os.environ.items() if not k.startswith(('PIP_', 'PYTHON'))}
        env['PIP_CONFIG_FILE'] = os.devnull
        return operation.command([str(python), '-m', 'pip', '--isolated', '--disable-pip-version-check',
                                  '--cache-dir', str(self.root / 'pip-cache'), *args], env=env)

    def install(self, lock, key, operation):
        if not lock['wheels']:
            if any(lock['runtime'][key] != self.runtime[key] for key in ('pydantic', 'packaging')):
                raise failed('DEPENDENCY_ERROR', '平台 SDK 基础依赖版本已变化，请使用历史实例对应的 Python 环境')
            return Path(sys.executable)
        target = self.root / 'environments' / key
        python = target / 'bin' / 'python'
        ready = target / 'ready.json'
        if ready.is_file() and python.is_file() and json.loads(ready.read_text()) == lock:
            operation.report('verify', message='复用锁定环境')
            self.pip(python, ['check'], operation)
            actual = json.loads(operation.command([str(python), '-c',
                'import importlib.metadata as m,json;print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version for d in m.distributions()}))']))
            if any(actual.get(w['name']) != w['version'] for w in lock['wheels']):
                raise failed('DEPENDENCY_CONFLICT', '缓存环境中已安装版本与实例锁不一致，请恢复对应缓存')
            return python
        target.parent.mkdir(exist_ok=True)
        with self.mutex('env-' + key, operation):
            # 环境目录使用唯一锁摘要；旧实例引用的其他环境不做清理。
            wheelhouse = self.root / 'wheels' / key
            wheelhouse.mkdir(parents=True, exist_ok=True)
            requirements = []
            for wheel in lock['wheels']:
                blob = self.download(wheel['url'], wheel['sha256'], operation)
                file = wheelhouse / wheel['filename']
                shutil.copyfile(blob, file)
                requirements.append(f'{wheel["name"]}=={wheel["version"]} --hash=sha256:{wheel["sha256"]}')
            requirement_file = wheelhouse / 'requirements.txt'
            requirement_file.write_text('\n'.join(requirements) + '\n')
            if target.exists():
                shutil.rmtree(target)
            python = self.create_environment(target, operation)
            self.pip(python, ['install', '--no-index', '--find-links', str(wheelhouse), '--only-binary=:all:', '--require-hashes', '-r', str(requirement_file)], operation)
            self.pip(python, ['check'], operation)
            ready.write_text(json.dumps(lock, sort_keys=True))
            return python
