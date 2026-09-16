const { spawn } = require('node:child_process');
const { once } = require('node:events');
const assert = require('node:assert/strict');
const net = require('node:net');
const path = require('node:path');
const readline = require('node:readline');
const electron = path.join(__dirname, '../node_modules/electron/dist/electron');

async function verify(parentKill) {
  const env = { ...process.env }; delete env.ELECTRON_RUN_AS_NODE;
  const parent = spawn(electron, [path.join(__dirname, 'lifecycle-child.cjs'), ...(parentKill ? ['--parent-kill'] : [])], { env, stdio: ['ignore', 'pipe', 'inherit'] });
  const exit = once(parent, 'exit');
  let ready;
  const timer = setTimeout(() => parent.kill('SIGKILL'), 15000);
  try {
    for await (const line of readline.createInterface({ input: parent.stdout })) {
      if (line.startsWith('LIFECYCLE ')) {
        ready = JSON.parse(line.slice(10));
        if (parentKill) parent.kill('SIGKILL');
      }
    }
    const [code, signal] = await exit;
    assert.ok(ready, 'backend must handshake before test action');
    assert.equal(parentKill ? signal : code, parentKill ? 'SIGKILL' : 0);
    // 明确等待同一 PID 消失；不是固定延时后假定退出。
    const deadline = Date.now() + 5000;
    while (true) {
      try { process.kill(ready.pid, 0); }
      catch (error) { if (error.code === 'ESRCH') break; throw error; }
      assert.ok(Date.now() < deadline, 'orphan backend process');
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    const address = new URL(ready.address);
    const server = net.createServer();
    server.listen(Number(address.port), address.hostname);
    await once(server, 'listening');
    await new Promise((resolve) => server.close(resolve));
    console.log(`T09 PASS: ${parentKill ? 'parent SIGKILL → EOF' : 'last window closed'}; backend and port released`);
  } finally {
    clearTimeout(timer);
    if (parent.exitCode === null && parent.signalCode === null) parent.kill('SIGKILL');
    if (ready) { try { process.kill(ready.pid, 'SIGKILL'); } catch {} }
  }
}
(async () => { await verify(false); await verify(true); })().catch((error) => { console.error(error); process.exitCode = 1; });
