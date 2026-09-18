/* 使用桌面实际 Backend 管理器和真实数据库，所有数据放在临时目录。 */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { Backend } = require('../desktop/main/backend.cjs');
const managerPath = require.resolve('../desktop/main/backend.cjs');

async function exists(filename) {
  try { await fs.access(filename); return true; } catch { return false; }
}
async function waitUntil(predicate) {
  const deadline = Date.now() + 15000;
  while (!(await predicate())) {
    if (Date.now() > deadline) throw new Error('退出清理超时');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
}
async function request(backend, route, body) {
  const result = await fetch(backend.address + '/api/v1' + route, {
    method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  assert.ok(result.ok, 'HTTP ' + result.status);
  return result.json();
}

test('desktop starts persistent backend, restores data, rejects second owner and stops PostgreSQL', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'agent-desktop-test-'));
  let backend = new Backend({ dataDirectory: directory });
  try {
    await backend.start();
    const info = await request(backend, '/platform');
    assert.equal(info.persistent, true);
    assert.equal(info.dataDirectory, directory);
    const draft = await request(backend, '/drafts', { content: { name: 'desktop persistence' } });
    const other = new Backend({ dataDirectory: directory });
    await assert.rejects(other.start(), /已有后端/);
    await other.stop();
    assert.equal((await request(backend, '/health')).status, 'ready');
    await backend.stop();
    assert.equal(await exists(path.join(directory, 'postgresql/postmaster.pid')), false);
    backend = new Backend({ dataDirectory: directory });
    await backend.start();
    const restored = await request(backend, '/drafts/' + draft.draftId);
    assert.equal(restored.content.name, 'desktop persistence');
  } finally {
    await backend.stop();
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test('forced backend termination preserves data and next launch reclaims its PostgreSQL', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'agent-desktop-crash-'));
  let backend = new Backend({ dataDirectory: directory });
  try {
    await backend.start();
    const draft = await request(backend, '/drafts', { content: { name: 'before crash' } });
    const exit = once(backend.child, 'exit');
    backend.child.kill('SIGKILL');
    await exit;
    await backend.stop();
    backend = new Backend({ dataDirectory: directory });
    await backend.start();
    assert.equal((await request(backend, '/drafts/' + draft.draftId)).content.name, 'before crash');
  } finally {
    await backend.stop();
    assert.equal(await exists(path.join(directory, 'postgresql/postmaster.pid')), false);
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test('desktop parent disappearing closes backend transport and local PostgreSQL', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'agent-parent-crash-'));
  const code = `const { Backend } = require(process.argv[1]);
    const backend = new Backend({ dataDirectory: process.argv[2] });
    backend.start().then(() => process.send('ready')).catch(() => process.exit(1));`;
  const parent = spawn(process.execPath, ['-e', code, managerPath, directory], {
    stdio: ['ignore', 'inherit', 'inherit', 'ipc'],
  });
  try {
    const ready = await Promise.race([
      once(parent, 'message'),
      once(parent, 'exit').then(() => { throw new Error('parent exited before ready'); }),
    ]);
    assert.equal(ready[0], 'ready');
    const exit = once(parent, 'exit');
    parent.kill('SIGKILL');
    await exit;
    await waitUntil(async () => !(await exists(path.join(directory, 'postgresql/postmaster.pid'))));
    // 目录锁也必须释放，随后可立即重新打开。
    const reopened = new Backend({ dataDirectory: directory });
    try { await reopened.start(); } finally { await reopened.stop(); }
  } finally {
    if (parent.exitCode === null && parent.signalCode === null) parent.kill('SIGTERM');
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test('closing during initial startup leaves no database process', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'agent-startup-stop-'));
  const backend = new Backend({ dataDirectory: directory });
  try {
    const starting = backend.start();
    const rejected = assert.rejects(starting);
    await backend.stop();
    await rejected;
    assert.equal(await exists(path.join(directory, 'postgresql/postmaster.pid')), false);
  } finally {
    await backend.stop();
    await fs.rm(directory, { recursive: true, force: true });
  }
});
