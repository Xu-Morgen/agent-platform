# 业务包接入与查重操作

从仓库根目录运行下列命令，使用已有 `.venv` 依赖。平台、包和实例都是受信任的本地 Python 源码，非沙箱；本例不需要安装新依赖。独立后端与桌面后端是不同会话，不共享内存。

## 无真实模型的接入演示

```bash
.venv/bin/python checks/similarity_onboarding.py
```

脚本启动全新后端进程和本地 HTTP 模型协议替身（分别验证 OpenAI 兼容与 Ollama），通过与下方相同的接入脚本创建环境、加载包与单文件块、解析拼图、保存、提交并查询双报告，再关闭后端并验证重启后原任务 404。替身只验证接线和契约，不代表 M2 真实模型验收。

## 使用远程 OpenAI 兼容模型 API

1. 在终端 A 启动后端：

   ```bash
   .venv/bin/python -m agent_platform --port 8000
   ```

2. 在终端 B 调用接入样例，把地址和模型名替换为服务商提供的实际值，并预先设置 MODEL_API_KEY 环境变量：

   ```bash
   .venv/bin/python samples/invoke_similarity.py \
     --adapter openai-chat \
     --model-url https://api.openai.com/v1 \
     --model YOUR_MODEL_NAME \
     --credential-env MODEL_API_KEY \
     --non-strict \
     --input samples/assignment-similarity/examples/input.json \
     --output /tmp/similarity-report.json
   ```

   后端地址可用 `--platform-url` 指定。模型需要认证时，预先在本机环境中设置凭据，再使用 `--credential-env 环境变量名`；不把密钥写入示例或命令参数。`--timeout` 默认 180 秒，为模型传输超时设置。

   样例调用已有 HTTP API，要求后端与脚本共享文件系统：先创建环境，加载目录资源，将 `flows/similarity.json` 的资源/环境占位符解析为实际引用，以 `{name, flow}` 保存。执行使用完整内存快照。不会修改仓库默认配置。

3. 脚本等待终态，输出状态、服务/任务 ID、实际模式、usage 和两类报告。失败返回非零退出码及具体错误，不发布部分成功报告。`--output` 导出不含原输入、环境地址或凭据引用；模型 reason/suggestion 可能引用输入，分享报告前仍需审阅内容。
4. 终端 A 按 Ctrl+C 停止后端。桌面会话关闭窗口退出，立即中止本地模型传输。主动取消任务使用 `POST /api/v1/runs/{runId}/cancel`，会等当前模型传输结束，超时或断连仍为 failed。

默认实例配置是 loopLimit=1、tokenLimit=32768、strictTokenLimit=true。当前 OpenAI 兼容与 Ollama 适配器均没有输入 token 上界预检，严格模式会在发送前返回 `TOKEN_ACCOUNTING_UNSUPPORTED`。上例的 `--non-strict` 是显式选择，不是自动降级；仍执行 token 账本及超额检查。模型缺失可用 usage 时失败，不按零消耗处理。模型上下文容量由已有部署保证，平台不自动下载模型、扩大上下文或重试。

远程 API 默认使用 `max_completion_tokens` 和 JSON 模式，兼容服务可显式追加 `--output-token-parameter max_tokens` 或 `--no-json-mode`。baseUrl 不含 `/chat/completions`，平台追加该路径。完整启动和隐藏输入 Key 的命令见 [项目 README](../readme.md#快速启动)。

Ollama 用户须显式添加 `--adapter ollama-chat`，将 `--model-url` 改为服务根地址（如 `http://127.0.0.1:11434`），模型名填已有部署；不要求所有用户安装 Ollama。

## API 和桌面等价步骤

| 步骤 | 既有接口或动作 |
| --- | --- |
| 创建环境 | `POST /api/v1/environments`，模型连接 connectionId=model、kind=model、modelAdapter=openai-chat、baseUrl（含 /v1）、model；保存返回 environmentId |
| 加载模块 | `POST /api/v1/catalog/load`，包路径 `packages/semantic`、块路径 `blocks/clean.py`、`score.py`、`adapt.py`、`assemble.py` |
| 准备拼图 | 服务页面选择输入输出契约，拼清洗→计分→适配→语义→组装；逐节点明确来源，语义包弹窗绑定实际环境连接 |
| 保存服务 | `POST /api/v1/services`，`{name, flow: 完整FlowDraft}`；成功即生成当前实例与稳定 serviceId |
| 提交调用 | `POST /api/v1/runs`，`{serviceId, input: {targetText, comparisonTexts}}` |
| 状态和结果 | `GET /api/v1/runs/{runId}`；completed 后 `GET /api/v1/runs/{runId}/result` |

桌面环境页填写 Base URL 和凭据，获取并选择模型后保存。服务页操作参见 [查重拼图说明](assignment-similarity/README.md)。也可使用配方辅助导入草稿：

```bash
.venv/bin/python samples/flow_templates.py samples/assignment-similarity similarity --platform-url 实际后端地址 --environment-id 实际环境ID --non-strict
```

随后点击桌面“检查健康状态”刷新目录与草稿，从会话草稿选择“文本查重”，检查节点配置后“校验并保存实例版本”。无需手写 instance.json 或 capabilityBindings。路径由同机后端读取，不上传目录。

所有环境、凭据、配置版本、任务和报告仅在当前后端内存。重启需重新创建/加载，旧 runId 返回 404，历史不可回退；显式导出的 JSON 文件仍保留在磁盘，不会自动导入恢复。

## 模板与验证入口

- [标准模板](template/README.md)：单文件块、控制流及同包双节点配置；复制重命名验证：`.venv/bin/python checks/template_copy.py`。
- [查重产品](assignment-similarity/README.md)：算法边界与契约。
- 合成契约与清洗：`checks/similarity_contracts.py`、`checks/similarity_preprocessing.py`。
- 计分和现有 DOCX：`.venv/bin/python checks/similarity_scoring.py --artifact-dir artifact`，只在本地提取及计分，不调用模型、不提交原文。
- 新版查重拼图：`.venv/bin/python checks/similarity_flow.py`，使用本地 HTTP 替身；旧 `similarity_workflow.py` 仅属 I5 历史入口。
