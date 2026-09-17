# 完整业务包：配置与能力扩展示例

本例保留一个模型交互单元，展示输入准备、可选指导查询、模型调用及输出验证。

```text
Input(text, topic)
  → normalize 块能力：去掉首尾空白
  → guidance API 能力：按配置选择是否查询指导
  → 读取 prompt.txt，叠加实例指令和输出风格
  → chat 模型能力：生成摘要和关键词
  → 校验 ModelSummary 及关键词数量
  → Output(text, keywords, sourceCharacters)
```

## 输入、输出和业务配置

输入：

```json
{"text":"  平台支持资源管理与任务执行。  ","topic":"general"}
```

输出形状示例（摘要/关键词由真实模型决定）：

```json
{"text":"平台支持资源管理和任务执行。","keywords":["资源管理","任务执行"],"sourceCharacters":14}
```

| 字段 | 默认值/约束 | 用途 |
| --- | --- | --- |
| Input.text | 必填，1～10000 字符 | 模型待处理数据，整理后还会检查非空 |
| Input.topic | general，非空字符串 | 指导 API 查询主题 |
| Output.text | 必填，非空字符串 | 模型摘要 |
| Output.keywords | 1～10 个非空字符串 | 模型关键词；运行时还检查节点 keywordLimit |
| Output.sourceCharacters | 正整数 | 包使用 len 确定性计算的整理后文本码点数 |
| parameters.instruction | 准确概括事实，不补充原文之外的信息。 | 附加系统指令，拒绝纯空白 |
| parameters.maxOutputTokens | 512，范围 64～4096 | 单次模型输出请求上限，可被平台余额收紧 |
| parameters.useGuidance | false | 是否调用指导 API；不取消清单中的绑定要求 |
| parameters.style | 默认 Style 对象 | 嵌套配置 |
| parameters.style.language | zh，可选 zh/en | 写入模型提示的输出语言；未增加语言检测器 |
| parameters.style.keywordLimit | 3，范围 1～10 | 写入提示且在模型返回后强制校验数量 |

完整节点参数见 [node-configuration.example.json](node-configuration.example.json)。配置不存在的字段会被拒绝，预算字段不能重复写进 parameters。省略的业务字段由 Config 默认值补齐；字段注释通过 JSON Schema 导出，页面尚未完整呈现的嵌套配置可用 API JSON 设置。

## 三个能力如何绑定

| capabilityId | kind | 输入 → 输出 | 节点中绑定什么 |
| --- | --- | --- | --- |
| normalize | block | Text → Text，即 `{"text":"..."}` | 加载 [blocks/minimal.py](../../blocks/minimal.py) 后返回的 resourceId |
| guidance | api | `{"topic":"general"}` → `{"instruction":"..."}` | API 环境及连接、POST、`/guidance` |
| chat | model | 平台 ModelRequest → ModelResponse | 模型环境及连接 |

normalize 绑定的是 **最小块**，完整块的输出带额外统计字段，不能直接满足此 Text 能力契约。Text 在包内自包含定义，没有运行时读取外部 samples 文件的依赖。

guidance 需要由使用者提供兼容的外部 HTTP 服务：请求方法 POST，路径由节点配置决定，JSON 请求体只有 topic，成功响应直接返回非空 instruction 字符串字段，不能包装在 data 中。模板不包含 API 替身或服务端。默认 useGuidance=false，不会发送 API 请求，但当前平台要求全部声明能力都具备合法绑定，因此仍须保存 API 连接。只想配置模型时使用最小包。

## 配置与运行

1. 加载最小通用块及本包目录。
2. 保存包含模型连接和 API 连接的环境；也可以使用两个环境。
3. 插入包节点 `summarize`，使用本包发布的 inputContract/outputContract，并接完整输入/输出。
4. 将示例节点 JSON 中的环境 ID、连接 ID、块资源 ID 替换为真实值，填到 `nodeConfigurations.summarize`。
5. 配置服务全局预算 `{"loopLimit":1,"tokenLimit":32768,"strictTokenLimit":false}`，预检并保存实例。
6. 提交输入。需要 API 指导时将 useGuidance 改为 true，保存新实例版本。

一次执行调用模型一次，计包 loop 一次。内部块/API 调用不会额外增加包 loop。两个检查点不创建自定义进度日志。输入为空白、API/模型失败、模型字段错误或关键词超限都会使任务失败，不返回部分报告。

这里没有 on_start/on_finish 生命周期配置，没有包内图、自动重试或自动修复模型 JSON。完整清单字段和连接参数见 [CONFIGURATION.md](../CONFIGURATION.md)，全部上下文接口和可用钩子见 [CONTEXT.md](../CONTEXT.md)。
