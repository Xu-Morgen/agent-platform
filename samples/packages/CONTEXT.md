# 平台标准执行入口

核对日期：2026-09-24。所有业务包统一使用平台入口，不接收运行上下文。每次调用执行以下步骤：

1. 平台检查取消状态、任务和节点预算，并登记一次调用。
2. 按输入契约验证节点输入，按可选 Config 验证业务参数。
3. 从固定快照读取 Prompt，替换预留字段。
4. 构造平台 ModelRequest，发起一次模型调用并记录用量。
5. 校验 ModelResponse，再按包输出契约严格验证 response.output。
6. 返回校验后的业务对象；任何校验失败都使步骤失败。

平台保留模型请求和响应的内置契约检查。系统消息包含由包输出契约生成的 JSON Schema，渲染后的 Prompt 作为 user 消息发送。模型仍可能返回不合法内容，最终以程序校验为准。输出不符合契约时，流程执行器按服务 retryLimit 重新调用该包，达到上限后报错；每次调用都计预算。不修复 JSON，不做字段改名或包装解包。

## Prompt 占位符

```text
请使用 {{parameters.style.language}} 概括以下文本：
{{input.primary.text}}
```

- input 指已通过契约校验的 NodeInput，包含 primary 和固定位置 references。
- parameters 指已验证并补默认值的节点业务参数。
- 路径使用对外 JSON 字段名，例如 {{input.primary.sourceText}}；支持嵌套对象字段，以及固定元组索引，例如 {{input.references[0].text}}。
- {{input}} 或 {{parameters}} 可插入整个对象。
- 字符串原样填入；对象、数组、数字、布尔和 null 采用 JSON 表示。
- 只替换一次，输入文本中出现的占位符不会再次执行。
- 不支持表达式、函数、过滤器、动态数组索引或条件模板；单个 JSON 花括号可直接书写，双花括号保留给占位符。
- 加载时检查模板语法及契约字段。可空/联合类型的内部字段不能直接访问，可插入整个值，或用上游通用块准备确定结构。

字符数计算、清洗、拆分、排序、外部查询和结构转换都由通用块完成，再通过接线传入包。包契约只定义和验证数据结构，不承担数据加工。

## 协议与错误

平台 ModelRequest 包含 messages 和 maxOutputTokens；模型响应包含 JSON output 和 usage。业务输出只返回 output 经包契约校验后的值，不混入模型用量。用量在任务/步骤记录中查询。

Prompt 文件丢失、占位符错误在加载时报 CONFIGURATION_ERROR；业务输入错误报 CONTRACT_VALIDATION_ERROR；模型响应或业务输出错误报 OUTPUT_VALIDATION_ERROR。预算、取消、传输错误保留平台各自的错误语义，不返回固定成功内容。

资料不足时允许返回保留的失败对象 `{"error":"INSUFFICIENT_INPUT"}`（必须完全相同，不加字段）。这是平台失败协议，不属于业务输出契约：平台在记录实际模型用量后以 PACKAGE_INPUT_INSUFFICIENT 终止，不触发格式重试，不把错误对象返回为成功结果。完整模板 Prompt 已包含此用法。

只发送 Prompt 占位符明确引用的数据，不自动附加 references；声明引用的全文与 Prompt 均原样发送，不能静默截断。平台当前没有统一的模型 tokenizer 或上下文容量预检；模型输出额度和累计 token 预算不等于上下文容量。上下文超限和传输错误的映射见 [模型协议](../../docs/protocols/model.md#openai-兼容远程-chat-completions)。业务连接及预算配置见 [文档出题实例](../../examples/document-question-generation/README.md#模型连接和预算)。

包不维护运行钩子、检查点或取消处理；平台统一执行 [取消与退出规则](../../docs/architecture-design.md#8-状态机取消与退出)。
