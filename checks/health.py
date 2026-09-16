"""真实子进程启动及端口释放，不使用 HTTP 替身。"""
import socket
import subprocess
import sys
import time
import urllib.request
import json

with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
process = subprocess.Popen([sys.executable, '-m', 'agent_platform', '--port', str(port)], stderr=subprocess.PIPE)
try:
    for _ in range(100):
        if process.poll() is not None:
            raise AssertionError(process.stderr.read().decode())
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health', timeout=1) as response:
                assert json.load(response) == {'status': 'ready'}
            break
        except OSError:
            time.sleep(.05)
    else:
        raise AssertionError('backend startup timeout')
finally:
    process.terminate()
    process.wait(timeout=5)
with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', port))
print('T05 PASS: real health ready and listening port released')
