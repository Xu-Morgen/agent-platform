# 模型协议：OpenAI 兼容 Chat Completions

更新日期：2026-09-24。本文描述仓库模型适配器的行为；公开字段以 `contracts/models.py`、`contracts/environments.py` 及 OpenAPI 为准。

## 连接字段与默认值

环境页和 `POST /api/v1/environments` / `PUT /api/v1/environments/{environmentId}` 保存模型或 API 连接。连接支持 `credential`（写入新凭据）或 `credentialRef`（引用已保存凭据），二者互斥，也可同时省略；凭据不进入包或 Prompt。Base URL 必须是无认证信息、query 或 fragment 的 HTTP(S) 地址。存储和密钥恢复由 [持久化手册](../persistence.md) 维护。

HTTP 环境写入省略 timeoutSeconds 时默认为 60 秒；桌面新建模型连接初始值为 180 秒，新建 API 连接为 60 秒，执行使用最终保存的值。模型的输出参数和 JSON 模式默认行为见 [Chat Completions 协议](#openai-兼容远程-chat-completions)；API 请求另外受 [块整体执行时限](../platform-runtime-files.md#环境缓存及运行) 限制。包节点如何引用模型连接见 [配置示例](../../samples/packages/CONFIGURATION.md#模型环境)。

## 草稿连接诊断

环境配置页支持模型和 API 两类连接。模型连接表单包含 Base URL、凭据、超时和模型下拉选择；API 连接不提供模型发现或测试，具体请求路径在通用块节点中配置。修改地址或凭据后须重新获取模型，页面不提供手动模型输入。outputTokenParameter 和 jsonMode 可通过 HTTP 环境配置写入，当前页面没有对应编辑控件。环境配置页与 HTTP 调用方共用两个通用接口：

| 接口 | 请求 | 成功响应 |
| --- | --- | --- |
| `POST /api/v1/connection-tools/models` | `{"connection": {...}}`，模型连接的 `model` 可省略 | `models` 字符串数组、`elapsedMs` |
| `POST /api/v1/connection-tools/test` | `{"connection": {...}, "maxOutputTokens": 256}`，必须指定模型 | `status: "passed"`、`elapsedMs`、`usage` |

权威契约为 `contracts/connection_tools.py`，公开 Schema 随 FastAPI OpenAPI 导出。连接字段沿用上节环境写入契约；诊断所用临时凭据不写入环境或共享凭据仓储。诊断只支持 `kind: "model"`。模型列表使用 OpenAI 兼容 `GET /models` ；路径拼接保留用户提供的 Base URL 前缀。

推理测试复用实际适配器，按配置发送输出参数与 JSON 模式，要求响应完成且输出为 `{"ok": true}`。桌面测试输出上限为 256；HTTP 调用方可设为 16–8192。列表成功仅代表列表接口可用；测试通过仅代表此小型请求可用，不等于业务图、累计 token 预算或远端计费验收。请求不自动重试，不创建运行任务。错误使用平台脱敏契约：非成功 HTTP 响应附带 httpStatus，超时附带 timeoutSeconds；连接失败等其他错误不保证包含这两项，不返回上游原始错误。诊断超时遵循连接配置，桌面退出时关闭在途传输。

## OpenAI 兼容远程 Chat Completions

平台使用 OpenAI 兼容协议。`baseUrl` 填 API 根路径，例如 `https://api.openai.com/v1` 或兼容服务商提供的地址；平台追加 `/chat/completions`，不自动追加 `/v1`。请求用 `stream=false`、messages、model，凭据通过平台凭据仓储解密读取并注入 `Authorization: Bearer`。

依据：[OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。默认发送 `max_completion_tokens`；兼容服务仅支持旧参数时，环境显式设置 `outputTokenParameter: "max_tokens"`。默认 `jsonMode: true` 发送 `response_format: {"type":"json_object"}`；不支持该参数的端点可以显式设为 false，平台仍要求响应内容为合法 JSON。不会自动重试或更换参数。

仅接受单个 choice、finish_reason=stop、assistant 文本，拒绝截断、工具调用、拒绝回答和非法 JSON。prompt_tokens 和 completion_tokens 必须为非负整数；total_tokens 若提供则必须与两者之和相等。推理 token 明细不再重复累计。exact 表示采用供应商报告计数，不代表已验证远程计费。缺少 usage 返回 unsupported，任务预算据此明确失败；请求额度收紧与累计规则见 [架构预算说明](../architecture-design.md#93-token-计量)。

HTTP 非成功响应中的顶层 usage 使用相同规则校验；合法用量仍交给任务记账，不公开响应原文。usage 缺失或无效时记为未知，并保留原 HTTP 错误，不用计量错误覆盖它。

平台没有统一 tokenizer 预检；供应商在 HTTP 400、413 或 422 响应中明确返回 context_length_exceeded、context_window_exceeded 或 max_context_length_exceeded 时映射为 MODEL_CONTEXT_EXCEEDED，不回显上游原文。其他 HTTP 错误保持原有状态与传输语义。包资料不足的保留失败对象由 [包执行说明](../../samples/packages/CONTEXT.md#协议与错误) 定义。

桌面编辑模型连接的 Base URL 时，会按主机名重新设置 outputTokenParameter：api.deepseek.com 使用 max_tokens，其他主机使用 max_completion_tokens，覆盖此前通过 HTTP 保存的自定义值。仅加载连接或保存而不修改地址、连接类型时保留已有值；切换为模型连接会重新初始化 outputTokenParameter 和 jsonMode。兼容服务需要自定义参数时，应先完成页面地址修改并保存，再通过 HTTP 环境配置写入所需参数，然后重新读取已保存的连接进行测试。

文档出题的模型与额度配置见 [模型连接和预算](../../examples/document-question-generation/README.md#模型连接和预算)。

## 节点输入与 Prompt

包入口、Prompt 占位符和发送范围统一见 [包执行说明](../../samples/packages/CONTEXT.md)。节点输入与参考在请求前严格校验；上游重试归因见 [架构说明](../architecture-design.md#58-节点输入校验与重试)。
