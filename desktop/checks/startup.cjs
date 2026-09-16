const assert = require('node:assert/strict');
const net = require('node:net');
const { once } = require('node:events');
const { Backend } = require('../main/backend.cjs');

(async () => {
  const occupied = net.createServer();
  occupied.listen(0, '127.0.0.1');
  await once(occupied, 'listening');
  const failed = new Backend({ port: occupied.address().port });
  try {
    await assert.rejects(failed.start(), /监听或启动失败/);
    assert.equal(failed.address, null);
  } finally {
    await failed.stop();
    await new Promise((resolve) => occupied.close(resolve));
  }
  const cancelled = new Backend();
  const started = cancelled.start().then(() => { throw new Error('unexpected readiness'); }, () => {});
  await cancelled.stop();
  await started;
  assert.equal(cancelled.address, null);
  await assert.rejects(cancelled.start(), /正在退出/);
  console.log('startup PASS: occupied port produces startupError; closing during startup cannot restore readiness');
})().catch((error) => { console.error(error); process.exitCode = 1; });
