# I3 执行能力样例

这些样例用于验证平台执行链路。配置、任务、结果与凭据仅保留在当前进程内；未使用真实模型进行验收。loop/token 预算、主动取消和完整在途退出语义由 I4 接入，I3 的统一策略入口尚不提供受限执行保证。

## 无模型页面调用

1. 启动桌面，按 [配置样例](../configuration/README.md) 加载 identity 块、echo/second 包和实例并保存服务。
2. 在任务调用面板点击“填入输入样例”，提交 `{"text":"合成输入"}`。
3. 面板轮询 queued/running，completed 后显示最终对象和节点步骤。实例入口调用 `context.run_graph`，图及包均取提交时的固定快照。
4. 复制 runId，刷新页面后填入查询框，可查回同次运行内的任务。退出应用后任务不存在。

HTTP 使用同一能力：

```http
POST /api/v1/runs
Content-Type: application/json

{"serviceId":"svc_实际标识","expectedInstanceId":"ins_当前标识","input":{"text":"合成输入"}}
```

成功返回 202 的 Run 对象，包含新的 `runId`、`status=queued`、实际实例/版本、环境快照和输入。相同输入不去重；输入错误 422 或版本冲突 409 时不创建任务。省略 expectedInstanceId 则使用当前实例。

- `GET /api/v1/runs/{runId}` 返回状态、步骤、错误与模型步骤用量。
- `GET /api/v1/runs/{runId}/result` 在 completed 时返回 `{runId, instanceId, result}`；queued/running 返回 409 RESULT_NOT_READY，failed/cancelled 返回 409 和终态原因；未知记录为 404。
- 排队起占用所有引用环境，运行中仍占用，终态清理释放。更新占用环境返回 409 ENVIRONMENT_IN_USE 和 activeRunIds。

## 块与 API

实例调用 `await context.call_block('echo.identity', value)`。寻址格式为 `packageBindingId.capabilityId`，使用固定块内容与输入输出契约。`lms/` 是注册块样例，输出契约为 `{text: string}`；通用 `blocks.lms.unwrap` 的 bizData 契约由使用者传入。

API 能力绑定除 inputModel/outputModel 外，须显式填写 `kind=api`、environmentId、connectionId、apiMethod，可填 apiPath（以 `/` 开头的相对路径）。地址、超时与 credentialRef 取受理时的环境副本；可选凭据以 Bearer 方式发送。GET 输入作为查询参数，其余方法作为 JSON body；不跟随重定向、不自动重试。API 与块返回均校验，不把错误转换为空对象。

运行 `.venv/bin/python checks/api_execution.py` 可启动短暂的本地 HTTP 响应替身并验证成功、超时、错误契约及 LMS 解包。

## 模型与包

`model-package/` 为单次 LLM 交互模板，`model-instance/` 为组织它的实例图。使用前创建模型环境，设置服务根地址、`modelAdapter=ollama-chat`、model 标识与可选凭据，然后替换实例 JSON 内两处 `replace-with-environment-id`。加载包和实例后保存服务。

包通过 `context.call_model('chat', ModelRequest(...))` 请求模型，返回 ModelResponse（output + usage）；模型能力声明须引用 `agent_platform.contracts.models` 中的请求响应契约。实例用 `invoke_package(bindingId, input)` 调用包，每次尝试经过策略入口并记录 bindingId、attempt 和错误阶段；包上下文不提供调度其他包的接口。样例未隐藏重试。

协议、能力和严格计量限制见 [模型协议选择](../../docs/protocols/model.md)。无服务或密钥也可以执行 `.venv/bin/python checks/model_package.py`：固定图调用包，经真实 HTTP 协议访问本地替身，检查最终结果、模型步骤 usage 和环境释放。此命令不是模型质量或真实模型验收。

逐卡的其他定向命令与结果见 [I3 交接](../../docs/tasks/i3.md)。真实桌面验收命令：

```bash
env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/runs.cjs
```
