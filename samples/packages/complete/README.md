# 带参数的 Prompt 包

核对日期：2026-09-24。

展示输入输出结构约束、可选 Config、嵌套占位符和包预算默认值。仍只维护契约和 Prompt，不包含执行代码。

| 部分 | 字段及约束 |
| --- | --- |
| 主数据 | primary.text：1 到 10000 字符，由上游通用块准备 |
| 参考 | references[0].text：同样的文本约束，供事实核对 |
| 参数 | instruction：非空附加指令，有默认值 |
| 嵌套参数 | style.language：zh/en，默认 zh |
| 输出 | text：非空摘要；keywords：1 到 3 个非空关键词 |
| 预算建议 | loopLimit=4/tokenLimit=32768，作为节点默认值 |

Prompt 使用 {{parameters.instruction}}、{{parameters.style.language}} 、{{input.primary.text}} 和 {{input.references[0].text}}。关键词数量由 Output 的 Field 约束验证；需要不同结构时修改输出契约与 Prompt。跨步骤的动态业务规则用独立校验块处理。

加载目录、选择模型连接、配置参数后保存服务。节点示例见 [node-configuration.example.json](node-configuration.example.json)，模型环境和任务预算见 [配置参考](../CONFIGURATION.md)。Config 未填写的字段由契约补默认值；Config 不包含 token/loop 预算。

需要规范空白、查询资料或输出字符数时，在包前后放置通用块。包本身只通过 Prompt 使用已接入的数据。输出错误与资料不足的处理见 [标准入口](../CONTEXT.md#协议与错误)。

服务端口选择本包的 primaryContract/outputContract；唯一参考必须符合上表约束。独立运行及与块组合时的参考绑定、结构转换步骤统一见 [模板之间的接线](../../USAGE.md#模板之间的接线)。
