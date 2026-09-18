# 模型协议：OpenAI 兼容 Chat Completions

## 草稿连接诊断

环境配置页支持模型和 API 两类连接。模型连接表单包含 Base URL、凭据、超时和模型下拉选择；API 连接不提供模型发现或测试，具体请求路径在通用块节点中配置。修改地址或凭据后须重新获取模型，页面不提供手动模型输入。outputTokenParameter 和 jsonMode 可通过 HTTP 环境配置写入，当前页面没有对应编辑控件。环境配置页与 HTTP 调用方共用两个通用接口：

| 接口 | 请求 | 成功响应 |
| --- | --- | --- |
| `POST /api/v1/connection-tools/models` | `{"connection": {...}}`，模型连接的 `model` 可省略 | `models` 字符串数组、`elapsedMs` |
| `POST /api/v1/connection-tools/test` | `{"connection": {...}, "maxOutputTokens": 256}`，必须指定模型 | `status: "passed"`、`elapsedMs`、`usage` |

权威契约为 `contracts/connection_tools.py`，公开 Schema 随 FastAPI OpenAPI 导出。连接字段沿用环境写入契约，支持临时 `credential` 或已有 `credentialRef`，两者互斥；不写入环境或共享凭据仓储。诊断只支持 `kind: "model"`。模型列表使用 OpenAI 兼容 `GET /models` ；路径拼接保留用户提供的 Base URL 前缀。

推理测试复用实际适配器，按配置发送输出参数与 JSON 模式，要求响应完成且输出为 `{"ok": true}`。桌面测试输出上限为 256；HTTP 调用方可设为 16–8192。列表成功仅代表列表接口可用；测试通过仅代表此小型请求可用，不等于业务图、累计 token 预算或远端计费验收。请求不自动重试，不创建运行任务。错误使用平台脱敏契约：非成功 HTTP 响应附带 httpStatus，超时附带 timeoutSeconds；连接失败等其他错误不保证包含这两项，不返回上游原始错误。诊断超时遵循连接配置，桌面退出时关闭在途传输。

参考 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的草稿发现、临时凭据与手动模型选择交互；具体阅读了本机已安装 `@deepseek-ai/dsh-client-ui-settings-models` 的 `fetchModels` 和 `@deepseek-ai/dsh-llm-pi-ai` 的 `discoverModels` 实现。平台保留自身严格响应校验，不引入 dsh 依赖。


## OpenAI 兼容远程 Chat Completions

平台仅保留 OpenAI 兼容协议，不提供 modelAdapter 选择字段。`baseUrl` 填 API 根路径，例如 `https://api.openai.com/v1` 或兼容服务商提供的地址；平台追加 `/chat/completions`，不自动追加 `/v1`。请求用 `stream=false`、messages、model，凭据通过已有内存仓储注入 `Authorization: Bearer`。

依据：[OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。默认发送 `max_completion_tokens`；兼容服务仅支持旧参数时，环境显式设置 `outputTokenParameter: "max_tokens"`。默认 `jsonMode: true` 发送 `response_format: {"type":"json_object"}`；不支持该参数的端点可以显式设为 false，平台仍要求响应内容为合法 JSON。不会自动重试或更换参数。

仅接受单个 choice、finish_reason=stop、assistant 文本，拒绝截断、工具调用、拒绝回答和非法 JSON。prompt_tokens 和 completion_tokens 必须为非负整数；total_tokens 若提供则必须与两者之和相等。推理 token 明细不再重复累计。exact 表示采用供应商报告计数，不代表已验证远程计费。缺少 usage 返回 unsupported，预算策略明确失败。请求前限制单次输出，响应后累计检查节点和全局额度；单次请求可能超额，不提供严格上界保证。
