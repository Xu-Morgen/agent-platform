const { spawn } = require('node:child_process');
const path = require('node:path');
const readline = require('node:readline');
const { validate } = require('./validate.cjs');
const controlSchema = require('../contracts/control.schema.json');
const healthSchema = require('../contracts/health.schema.json');
const root = path.resolve(__dirname, '../..');

class Backend {
  constructor({ python = process.env.AGENT_PLATFORM_PYTHON || path.join(root, '.venv/bin/python'), port = 0 } = {}) {
    this.python = python;
    this.port = port;
    this.child = null;
    this.address = null;
    this.startPromise = null;
  }

  start() {
    if (this.startPromise) return this.startPromise;
    this.startPromise = new Promise((resolve, reject) => {
      let settled = false;
      const fail = (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.child?.kill();
        reject(error);
      };
      const timer = setTimeout(() => fail(new Error('后端启动超时')), 15000);
      this.child = spawn(this.python, ['-m', 'agent_platform', '--port', String(this.port), '--control-fd', '3'], {
        cwd: root, stdio: ['pipe', 'inherit', 'inherit', 'pipe'],
      });
      this.child.once('error', () => fail(new Error('无法启动 Python 后端，请检查解释器路径与依赖')));
      this.child.once('exit', () => {
        this.address = null;
        fail(new Error('后端在就绪前退出'));
      });
      const lines = readline.createInterface({ input: this.child.stdio[3] });
      let received = false;
      lines.on('line', async (line) => {
        try {
          const message = JSON.parse(line);
          if (!validate(controlSchema, message) || received || message.type === 'shutdown') throw new Error('后端控制消息无效');
          received = true;
          if (message.type === 'startupError') throw new Error(message.error.message);
          const response = await fetch(`${message.address}/api/v1/health`, { signal: AbortSignal.timeout(3000) });
          if (!response.ok || !validate(healthSchema, await response.json())) throw new Error('后端健康检查失败');
          if (settled) return;
          this.address = message.address;
          settled = true;
          clearTimeout(timer);
          resolve({ address: this.address, pid: this.child.pid });
        } catch (error) { fail(error); }
      });
    });
    return this.startPromise;
  }
}
module.exports = { Backend };
