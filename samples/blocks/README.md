# 创建通用块

核对日期：2026-09-24。

通用块是一个可独立加载的 `.py` 文件。无需 package.json。普通计算块只有业务输入；需要外部信息的块可通过 api=True 声明 API 能力，在节点上绑定 API 环境并配置请求路径。

## 最小实现

复制 [minimal.py](minimal.py)，修改 `id`、`name` 和函数体。页面选择“单文件通用块”，加载复制后的文件。

```json
{"text": "  hello  "}
```

输出：

```json
{"text": "hello"}
```

函数 `trim(value: NodeInput[Text, tuple[()]]) -> Text` 的参数类型是入口，返回值类型是出口。Text 的 `text: str` 必填，允许空字符串；纯空白输入会得到空字符串。平台先验证输入，再调用函数，最后验证返回值。

也可以直接用 `str`、`bool` 等类型，例如 `def is_ready(value: NodeInput[str, tuple[()]]) -> bool`；这时服务输入是 JSON 字符串，函数通过 value.primary 读取，输出是 JSON 布尔值。条件块必须返回严格 bool，不能用 0/1 替代。

## 最完整实现

[complete.py](complete.py)（`3.0.1`）在一个块内展示 API 能力、请求与响应契约、嵌套输入、默认值、枚举、自定义字段校验、可选任务附件、进度上报、显式业务错误与输出统计。执行顺序为检查附件 → 按 APIRequest 校验查询参数 → 查询 API → 严格验证响应 → 整理正文并检查 requireContent → 添加前缀 → 构造输出。源码包含分区中文讲解；模型文件接入为注释示范，默认不下载或运行模型。

运行前须在节点上绑定 API 连接并填写请求路径；本例在平台节点配置中填 `/lookup`，具体步骤见下方“完整块的 API 配置”。服务输入示例：

```json
{
  "query": "greeting",
  "options": {
    "trimEdges": true,
    "collapseSpaces": true,
    "letterCase": "upper",
    "prefix": "> "
  }
}
```

平台使用节点配置的路径，块传入 GET 方法和 query 参数，最终请求为 `GET /lookup?query=greeting`（相对于环境 Base URL）。块代码没有写死 `/lookup`。假设 API 返回以下 JSON：

```json
{"text": "  Hello\n  World  "}
```

最终输出：

```json
{"text": "> HELLO WORLD", "characterCount": 13, "changed": true}
```

| 输入配置 | 默认值/约束 | 作用 |
| --- | --- | --- |
| `query` | 必填，1～10000 字符且不能全为空白 | 发送给 API 的查询文本 |
| `options` | 可省略，生成 Options 默认实例 | 此次执行选项；不是节点 parameters |
| `options.trimEdges` | true | 去掉首尾空白 |
| `options.collapseSpaces` | true | 连续空白含换行合并为一个空格 |
| `options.letterCase` | preserve；可选 lower/upper | 转换字母大小写 |
| `options.prefix` | 空字符串，最长 20 字符 | 在其他处理完成后添加前缀 |
| `options.requireContent` | false | 开启后，整理后的正文必须含非空白字符；前缀不能代替正文 |
| `attachment` | null，可省略 | 平台生成的 PDF/DOCX 文件引用，示例检查并只读文件头 |

| 出口字段 | 类型 | 含义 |
| --- | --- | --- |
| `text` | str | 处理后的文本，允许为空 |
| `characterCount` | int ≥ 0 | 处理后文本的 Unicode 码点数，包含前缀 |
| `changed` | bool | 最终文本是否与 API 返回的原始文本不同，不与 query 比较 |

APIRequest 只包含 query；Input 继承它以复用字段约束，并增加本地 options 和 attachment。发送前重新构造 APIRequest，严格校验后序列化，避免将本地选项或文件引用发给外部服务。APIResponse 要求响应为仅包含 text 的对象，text 长度为 1～10000 字符；响应外壳需按实际接口调整。本例在校验通过后才处理文本，接口失败或响应不合法会直接使步骤失败。

例如只传 `{"query":"example"}`，若 API 返回 `{"text":" A  B "}`，使用默认选项输出 `{"text":"A B","characterCount":3,"changed":true}`。传 `{"query":12}` 或 `{"query":"x","unknown":true}` 会在发起请求前被入口校验拒绝。纯空白响应默认允许整理为空字符串；若开启 `options.requireContent`，则以 `CONTRACT_VALIDATION_ERROR`、`block.sample_normalize` 和 `options.requireContent` 字段位置明确失败，不添加前缀伪装为有效正文。

## @block 的全部配置

| 参数 | 是否必填/默认 | 作用 |
| --- | --- | --- |
| `id` | 必填 | 资源身份，以英文字母开头，仅字母、数字、下划线、连字符 |
| `version` | 必填 | `1.0.0` 或 `1.0.0-alpha` 格式；同 id/version 不允许内容不同，归档后也不释放版本号 |
| `name` | 必填，非空 | 页面展示名称 |
| `description` | 默认空字符串 | 用途说明，不影响执行 |
| `api` | 默认 false | 声明需要 API 连接；必须使用 async 函数并接收关键字参数 api: BlockAPI |
| `semanticSearch` | 默认 false | 声明本地语义检索；必须使用 async 函数并接收 context: BlockContext，提交时固定就绪的 embedding 模型；见 [接口](../../docs/local-embedding-contracts.md) |
| `ocr` | 默认 false | 声明本地 OCR；必须使用 async 函数并接收 context: BlockContext，提交时固定就绪的 OCR 模型组合；见 [接口](../../docs/local-ocr.md) |
| `dependencies` | 默认空列表 | PEP 508 包版本约束；交付时固定已验证版本 |
| `dependencySources` | 默认空列表 | 单一 HTTPS 索引或指定包的 HTTPS wheel URL 与 SHA-256 |
| `models` | 默认空列表 | 独立模型文件的 name/version/url/sha256/filename 清单 |

标准库、agent_platform 和 pydantic 无需额外声明；其他第三方导入必须声明。依赖来源、字面量检查及准备流程见 [运行文件规范](../../docs/platform-runtime-files.md#静态声明)。修改文件任意内容都会影响摘要，包括注释；重新加载修改版时必须更新 version。

## 可以使用的函数与校验钩子

最小模板使用同步 trim；完整模板使用异步 normalize，并接收 api/context。normalize_text 是文件内的普通辅助函数，APIRequest 的字段校验器供入口和外发请求共用；这些都不是额外注册入口或生命周期钩子。

合法签名与注入限制统一见 [研发手册](../../docs/external-development-guide.md#2-通用块的合法函数签名)，可用校验器见 [契约示例](../contracts/README.md)。源码组织、资源钩子与清理方式见 [开发约定](../../docs/external-development-guide.md#7-第三方依赖与运行生命周期)，执行时限和取消见 [运行生命周期](../../docs/platform-runtime-files.md#环境缓存及运行)。完整模板使用 PlatformError 报告明确业务失败，错误构造方式见 [错误与验证](../../docs/external-development-guide.md#8-错误验证与发布)。

## 输入参数怎么固定

块的业务选项包含在输入契约中；`nodeConfigurations` 为 API 块保存连接引用和请求路径。第一步自动接收服务完整输入，后续步骤自动接收上一层完整输出，主数据均须符合 Input 契约，平台再封装为 NodeInput；需要固定选项或拼装字段时，先通过另一个通用块处理。例如完整块节点：

```json
{
  "nodeId": "normalize",
  "kind": "block",
  "artifactRef": "替换为加载完整块返回的 resourceId"
}
```

调用数据可包含 options，例如 {"query":"内容","options":{"letterCase":"upper"}}；其余选项由 Options 默认值补齐；服务输入的 query 仍须满足块的长度约束，并为 normalize 节点配置下方的 API 连接和请求路径。最容易成功的接法是直接选择此块返回的 primaryContract/outputContract 作为服务端口，并采用完整输入/输出接线，见 [公共用法](../USAGE.md)。

## 完整块的 API 配置

[complete.py](complete.py) 声明 `@block(..., api=True)`，函数签名为 `async def normalize(value: NodeInput[Input, tuple[()]], *, api: BlockAPI, context: BlockContext) -> Output`。最小示例保持无外部依赖的零参考计算函数。

1. 在环境页添加 API 连接，填写 Base URL、可选 Bearer Token 和超时；API 连接不配置模型、不获取模型列表。
2. 加载 complete.py 并插入节点，点击节点配置选择 API 连接，填写“请求路径”（本例为 `/lookup`）。API 环境也可通过 HTTP 创建：

```json
{"name":"资料接口","connections":[{"connectionId":"lookup","kind":"api","baseUrl":"https://example.com/api","timeoutSeconds":60}]}
```

3. 在 `FlowDraft.nodeConfigurations.normalize` 中保存以下配置，包含连接引用和必填的 path，不包含模型、Prompt、loop/token 或业务参数：

```json
{"api":{"environmentId":"replace_environment_id","connectionId":"lookup","path":"/lookup"}}
```

4. 将服务输入接入该块，输入示例为 `{"query":"待查询内容"}`，也可添加 options；示例请求 `GET /lookup?query=...`，要求响应符合前述 APIResponse。更换路径只需修改节点配置；请求方法、参数生成和响应类型仍由块定义。此地址不是随项目提供的服务。
5. 将块输出接入服务出口；需要接入 Prompt 包时，按 [模板接线说明](../USAGE.md#模板之间的接线) 添加转换块并设置参考。只有通用块时无需模型环境或模型预算。

完整示例通过以下调用使用平台节点的路径：

```python
request = APIRequest(query=value.primary.query)
response = await api.request('GET', request.model_dump(mode='json', by_alias=True), response_type=APIResponse)
```

例如 Base URL 为 `https://example.com/api`、节点 path 为 `/lookup`，请求地址为 `https://example.com/api/lookup`。复用该模板的其他路径也必须接受相同参数并返回符合 APIResponse 的数据。

公开方法、路径限制、认证及请求/响应校验职责统一见 [API 接口规范](../../docs/external-development-guide.md#5-api绑定连接的-json-请求)。本块重试会再次请求 API，外部操作不回滚；重试范围见 [节点校验规则](../../docs/architecture-design.md#58-节点输入校验与重试)，取消与退出见 [状态机说明](../../docs/architecture-design.md#8-状态机取消与退出)。

## 文件与模型

完整示例的可选 `attachment: TaskFile | None` 会在任务页生成 PDF/DOCX 控件。保存完成后平台自动补入引用；手写本机路径不能替代文件上传。示例检查附件可用性并用 with 只读前 16 字节，未实现文档解析或 OCR。其他业务字段仍填写 JSON。

下载声明的准确字段、来源约束、缓存和超时说明见 [平台运行文件与依赖](../../docs/platform-runtime-files.md)。完整模板的依赖来源、模型清单为空，因此加载模板不会触发第三方包安装或模型下载。需要模型的块必须填写经过核验的真实地址与摘要，并把 `context.model(name)` 返回的路径显式传给推理库，禁止在任务函数中安装包或隐式下载模型。

## 进度与教学边界

完整块实际调用 `context.progress`：附件检查和 API 等待阶段只发送消息；API 响应校验后上报 `1 / 3`，文本整理后上报 `2 / 3`，输出构造成功后上报 `3 / 3`。任务页按相同通用协议显示，不需要针对块另写前端适配。API 或业务校验失败时不会报告后续阶段完成。

进度不是输出，也不是完整日志：平台保存步骤的最新进度，页面不保证展示每条短暂消息；`3 / 3` 仅表示块内处理完成，平台还会校验出口并运行后续节点。不能用 progress 代替逐框 OCR 诊断、审计事件或任务成功状态。

Input 使用 `field_validator` 演示纯空白查询校验。此校验无法完全表达为 JSON Schema，服务开始端口优先选本块导出的 primaryContract；与其他类型接线时仍以平台校验为准。源码说明了 model_validator 的适用场景、同步/异步入口、模型路径接入、本示例使用的装饰器参数、资源清理及取消/重试边界，没有声明或实现额外生命周期钩子。完整参数表见本页“@block 的全部配置”，semanticSearch/ocr 用法见相应接口手册。

教学示例的子进程/API/附件及失败边界验证见 [历史摘录](../../docs/archive/2026-09-24/manual-validation-excerpts.md#通用块教学示例验证)；不代表线上模型或完整桌面人工验收。

## NodeInput 与 Python 条件块

入口必须从 `agent_platform.contracts.node_input` 导入 `NodeInput`，声明 `NodeInput[主数据类型, tuple[参考类型, ...]]`；这里的省略号是文档示意，实际必须列出每个固定位置，不能使用变长 tuple[T, ...]。两套块模板均声明零参考 `tuple[()]`；首节点用简单模式，后接节点需配置高级空列表。输出保持业务类型。

在复制的最小块中可把返回注解改为 `bool`、函数体改为 `return bool(value.primary.text.strip())`，并更改 id/name/version，得到条件块；在 if 或 while 的条件位置选择它。条件独立执行，不替换分支或循环体的主数据。条件应只判断数据，避免外部 API 副作用；输入、输出错误不能当作 false。
