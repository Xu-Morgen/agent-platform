# 模型协议：OpenAI 兼容 API 与 Ollama

## 草稿连接诊断

环境配置页仅提供 Base URL、凭据输入与模型下拉选择；连接参数由表单生成。修改地址或凭据后须重新获取模型，页面不提供手动模型输入。环境配置页与 HTTP 调用方共用两个通用接口：

| 接口 | 请求 | 成功响应 |
| --- | --- | --- |
| `POST /api/v1/connection-tools/models` | `{"connection": {...}}`，模型连接的 `model` 可省略 | `models` 字符串数组、`elapsedMs` |
| `POST /api/v1/connection-tools/test` | `{"connection": {...}, "maxOutputTokens": 256}`，必须指定模型 | `status: "passed"`、`elapsedMs`、`usage` |

权威契约为 `contracts/connection_tools.py`，公开 Schema 随 FastAPI OpenAPI 导出。连接字段沿用环境写入契约，支持临时 `credential` 或已有 `credentialRef`，两者互斥；不写入环境或共享凭据仓储。诊断只支持 `kind: "model"`。模型列表使用 OpenAI 兼容 `GET /models` 或 Ollama `GET /api/tags`；路径拼接保留用户提供的 Base URL 前缀。

推理测试复用实际适配器，按配置发送输出参数与 JSON 模式，要求响应完成且输出为 `{"ok": true}`。桌面测试输出上限为 256；HTTP 调用方可设为 16–8192。列表成功仅代表列表接口可用；测试通过仅代表此小型请求可用，不等于业务图、严格总 token 预算或远端计费验收。请求不自动重试，不创建运行任务。错误使用原有脱敏契约（包含 HTTP 状态和超时时间），不会返回上游原始错误。诊断超时遵循连接配置，桌面退出时关闭在途传输。

参考 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的草稿发现、临时凭据与手动模型选择交互；具体阅读了本机已安装 `@deepseek-ai/dsh-client-ui-settings-models` 的 `fetchModels` 和 `@deepseek-ai/dsh-llm-pi-ai` 的 `discoverModels` 实现。平台保留自身严格响应校验，不引入 dsh 依赖。


## Ollama Chat

I3 选择 `ollama-chat`：POST `<baseUrl>/api/chat`，非流式 `stream=false`、`format=json`，文本 messages 与 `options.num_predict` 输出限额。这是最初实现的协议；baseUrl 配置为服务根地址。远程 OpenAI 兼容协议见下节。环境中的模型标识与可选 Bearer 凭据由平台注入，包不含地址或密钥。

依据：[Ollama Chat](https://docs.ollama.com/api/chat)、[官方 API 参数](https://github.com/ollama/ollama/blob/main/docs/api.md)。协议实现验证使用本地可控 HTTP 替身，本轮未重新验收真实模型或实际计费行为。

| 能力 | 声明 | 条件与边界 |
| --- | --- | --- |
| 响应输入/输出计量 | exact | 原样采用供应商 prompt_eval_count / eval_count，须为非负整数；这仅表示供应商报告的计数 |
| 请求前完整输入计量 | unsupported | 未安装 tokenizer，也未验证服务端模板、隐藏 token 和实际上下文 |
| 保守上界 | unsupported | 未证明总输入/输出的保守上界，不把字符数当上界 |
| 估算 | unsupported | 不以固定系数生成虚假估计 |
| usage 缺失 | unsupported | 返回明确的未知用量，不记为零；I4 计量策略据此报错 |
| 输出限额 | 支持参数 | num_predict 为正整数；仍需模型部署验收，隐藏/推理 token 未验证 |
| 严格总 token 保证 | 不支持 | 不能可靠预留完整输入；I4 严格模式在发送前拒绝 |
| 关闭传输 | 关闭本地连接 | 不保证远端停止计算或计费；正常取消由 I4 等待当前传输结束 |

平台请求/响应的权威来源为 `contracts/models.py`。`ModelResponse.output` 为解析后的 JSON，包输出仍按业务契约校验。无效 JSON、截断输出、拒绝响应、超时及传输错误均明确失败，不自动修复或重试。错误输出的供应商用量保留到步骤与 I4 账本。worker 按固定配置装配严格/非严格策略；完整输入预检接口 preflight 返回 ModelUsage（outputTokens=0），严格模式只接受 exact/upper_bound。Ollama 的 preflight 为 unsupported；严格支持路径仅用合成适配器验收。

## OpenAI 兼容远程 Chat Completions

现已支持 `modelAdapter: "openai-chat"`，通过固定环境配置选择，不要求安装本地模型。`baseUrl` 填 API 根路径，例如 `https://api.openai.com/v1` 或兼容服务商提供的地址；平台追加 `/chat/completions`，不自动追加 `/v1`。请求用 `stream=false`、messages、model，凭据通过已有内存仓储注入 `Authorization: Bearer`。

依据：[OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。默认发送 `max_completion_tokens`；兼容服务仅支持旧参数时，环境显式设置 `outputTokenParameter: "max_tokens"`。默认 `jsonMode: true` 发送 `response_format: {"type":"json_object"}`；不支持该参数的端点可以显式设为 false，平台仍要求响应内容为合法 JSON。不会自动重试或更换参数。

仅接受单个 choice、finish_reason=stop、assistant 文本，拒绝截断、工具调用、拒绝回答和非法 JSON。prompt_tokens 和 completion_tokens 必须为非负整数；total_tokens 若提供则必须与两者之和相等。推理 token 明细不再重复累计。exact 表示采用供应商报告计数，不代表已验证远程计费。缺少 usage 返回 unsupported，预算策略明确失败；无输入上界预检，因此严格总 token 模式仍在发送前拒绝，调用须显式选择非严格模式。
