# 带参数的 Prompt 包

展示输入输出结构约束、可选 Config、嵌套占位符和包预算默认值。仍只维护契约和 Prompt，不包含执行代码。

| 部分 | 字段及约束 |
| --- | --- |
| 输入 | text：1 到 10000 字符，由上游通用块准备 |
| 参数 | instruction：非空附加指令，有默认值 |
| 嵌套参数 | style.language：zh/en，默认 zh |
| 输出 | text：非空摘要；keywords：1 到 3 个非空关键词 |
| 预算建议 | loopLimit=1/tokenLimit=32768，作为节点默认值 |

Prompt 使用 {{parameters.instruction}}、{{parameters.style.language}} 和 {{input.text}}。关键词数量由 Output 的 Field 约束验证；需要不同结构时修改输出契约与 Prompt。跨步骤的动态业务规则用独立校验块处理。

加载目录、选择模型连接、配置参数后保存服务。节点示例见 [node-configuration.example.json](node-configuration.example.json)，模型环境和任务预算见 [配置参考](../CONFIGURATION.md)。Config 未填写的字段由契约补默认值；Config 不包含 token/loop 预算。

需要规范空白、查询资料或输出字符数时，在包前后放置通用块。该模板不再要求绑定 normalize/guidance，也不调用 API 或块。最终输出错误由平台拒绝，无固定成功内容或自动重试。
