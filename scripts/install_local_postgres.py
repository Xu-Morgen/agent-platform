"""Ubuntu 24.04 用户级 PostgreSQL 16 运行程序安装；由使用者显式执行。"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
        raise SystemExit('此安装脚本仅支持 Ubuntu 24.04；其他环境请安装 PostgreSQL 并设置 AGENT_PLATFORM_POSTGRES_BIN')
    target = Path.home() / '.local/share/agent-platform/postgresql'
    if target.exists():
        raise SystemExit(f'运行程序目录已存在，不自动覆盖或升级：{target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.postgresql-install-', dir=target.parent) as temporary:
        staging = Path(temporary)
        runtime = staging / 'runtime'
        runtime.mkdir()
        subprocess.run(['apt-get', 'download', 'postgresql-16', 'postgresql-client-16', 'libpq5'], cwd=staging, check=True)
        for package in staging.glob('*.deb'):
            subprocess.run(['dpkg-deb', '--extract', str(package), str(runtime)], check=True)
        binaries = runtime / 'usr/lib/postgresql/16/bin'
        env = {**os.environ, 'LD_LIBRARY_PATH': os.pathsep.join(str(p) for p in (runtime / 'usr/lib').glob('*-linux-gnu'))}
        for name in ('postgres', 'initdb', 'pg_ctl'):
            subprocess.run([str(binaries / name), '--version'], env=env, check=True)
        runtime.rename(target)
    print(f'已安装 PostgreSQL 运行程序：{target}')
    print('未创建系统服务；首次启动桌面时自动初始化应用自己的数据库。')


if __name__ == '__main__':
    main()
