# 模型协议：OpenAI 兼容 API 与 Ollama

I3 选择 `ollama-chat`：POST `<baseUrl>/api/chat`，非流式 `stream=false`、`format=json`，文本 messages 与 `options.num_predict` 输出限额。这是最初实现的协议；baseUrl 配置为服务根地址。远程 OpenAI 兼容协议见下节。环境中的模型标识与可选 Bearer 凭据由平台注入，包不含地址或密钥。

依据：[Ollama Chat](https://docs.ollama.com/api/chat)、[官方 API 参数](https://github.com/ollama/ollama/blob/main/docs/api.md)。协议实现验证使用本地可控 HTTP 替身，未验收真实模型或实际计费行为。

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

`.venv/bin/python checks/openai_chat.py` 已用本地 HTTP 替身验证路径、Bearer 认证、两种输出参数、JSON 开关、计量、截断/拒绝/畸形/超时、传输关闭及完整查重图。`.venv/bin/python checks/similarity_onboarding.py` 已验证两种协议从干净后端进程加载至双报告及重启清空。尚未提供实际远程地址、模型名与凭据，不能据此标记 I5-T08 真实验收完成。
