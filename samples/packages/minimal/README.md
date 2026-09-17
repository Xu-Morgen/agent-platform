# 最小业务包：一次模型交互

运行只需要 package.json、models.py、entry.py。模型将一段文本概括为 `{"text":"..."}`。没有外部 API、块能力、Prompt 文件或自定义配置参数。

| 项目 | 定义 |
| --- | --- |
| 输入 | models.Text：必填字符串 text |
| 输出 | models.Text：必填字符串 text，内容由模型生成 |
| 配置 | models.Config 继承 PackageBudget，只含预算字段 |
| 入口 | `entry:invoke`，接收 value/config/context |
| 能力 | chat：平台 ModelRequest → ModelResponse |
| 固定请求参数 | maxOutputTokens=256，在 entry.py 中设置 |

业务输入示例：

```json
{"text":"平台支持创建资源、拼接流程和执行任务。"}
```

输出形状示例（不保证真实模型逐字返回）：

```json
{"text":"平台支持资源管理、流程编排与任务执行。"}
```

## 操作

1. 在环境页配置模型协议、Base URL、模型名称及需要的凭据，保存后取得 environmentId 和 connectionId。
2. 在资源页加载本目录，插入包节点，nodeId 例如 `summarize`。
3. 选择此包返回的 inputContract/outputContract 作为服务入口/出口，接完整输入到包，包完整输出到服务出口。
4. parameters 填 `{}`；节点 budget 填 `{"loopLimit":1,"tokenLimit":32768}`；chat 绑定模型连接。
5. 服务全局 budget 填 `{"loopLimit":1,"tokenLimit":32768,"strictTokenLimit":false}`，然后保存实例并提交业务输入。

[node-configuration.example.json](node-configuration.example.json) 对应 `nodeConfigurations.summarize` 的值。将 environmentId/connectionId 替换为当前会话实际值；它不是包加载配置，不会自动生效。包不能自己选择部署环境。

`requiredCapabilities=[]` 的包在协议上可成立，但此模板保留一次模型调用来展示业务包的最小用途。Text 没有限制非空；如需限制，修改输入输出模型并同步 Prompt。模型返回结构错误时平台会拒绝结果，不以固定文本兜底。
