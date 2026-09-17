# 首个模型协议：Ollama 原生 Chat

I3 选择 `ollama-chat`：POST `<baseUrl>/api/chat`，非流式 `stream=false`、`format=json`，文本 messages 与 `options.num_predict` 输出限额。仅实现这一协议；baseUrl 配置为服务根地址。环境中的模型标识与可选 Bearer 凭据由平台注入，包不含地址或密钥。

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
