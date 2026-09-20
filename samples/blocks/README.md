# 创建通用块

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

函数 `trim(value: Text) -> Text` 的参数类型是入口，返回值类型是出口。Text 的 `text: str` 必填，允许空字符串；纯空白输入会得到空字符串。平台先验证输入，再调用函数，最后验证返回值。

也可以直接用 `str`、`bool` 等类型，例如 `def is_ready(value: str) -> bool`；这时输入是 JSON 字符串，输出是 JSON 布尔值。条件块必须返回严格 bool，不能用 0/1 替代。

## 最完整实现

[complete.py](complete.py)（`1.1.0`）在一个块内展示 API 能力、响应契约、嵌套输入、默认值、枚举、自定义字段校验、可选任务附件、进度上报、显式业务错误与输出统计。执行顺序为检查附件 → 查询 API → 严格验证响应 → 整理正文并检查 requireContent → 添加前缀 → 构造输出。源码包含分区中文讲解；模型文件接入为注释示范，默认不下载或运行模型。

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

APIResponse 要求响应为仅包含 text 的对象，text 长度为 1～10000 字符；响应外壳需按实际接口调整。本例在校验通过后才处理文本，接口失败或响应不合法会直接使步骤失败。

例如只传 `{"query":"example"}`，若 API 返回 `{"text":" A  B "}`，使用默认选项输出 `{"text":"A B","characterCount":3,"changed":true}`。传 `{"query":12}` 或 `{"query":"x","unknown":true}` 会在发起请求前被入口校验拒绝。纯空白响应默认允许整理为空字符串；若开启 `options.requireContent`，则以 `CONTRACT_VALIDATION_ERROR`、`block.sample_normalize` 和 `options.requireContent` 字段位置明确失败，不添加前缀伪装为有效正文。

## @block 的全部配置

| 参数 | 是否必填/默认 | 作用 |
| --- | --- | --- |
| `id` | 必填 | 资源身份，以英文字母开头，仅字母、数字、下划线、连字符 |
| `version` | 必填 | `1.0.0` 或 `1.0.0-alpha` 格式；同 id/version 不允许内容不同，归档后也不释放版本号 |
| `name` | 必填，非空 | 页面展示名称 |
| `description` | 默认空字符串 | 用途说明，不影响执行 |
| `api` | 默认 false | 声明需要 API 连接；必须使用 async 函数并接收关键字参数 api: BlockAPI |
| `dependencies` | 默认空列表 | PEP 508 包版本约束；交付时固定已验证版本 |
| `dependencySources` | 默认空列表 | 单一 HTTPS 索引或指定包的 HTTPS wheel URL 与 SHA-256 |
| `models` | 默认空列表 | 独立模型文件的 name/version/url/sha256/filename 清单 |

标准库、agent_platform 和 pydantic 无需在块的 dependencies 中额外声明。其他第三方导入必须声明；平台在独立环境中解析并安装 wheel，保存直接及传递依赖的版本、来源和摘要。不支持源码构建或安装脚本；PEP 508 中不直接填写 URL，指定下载源请使用 dependencySources。加载前用 AST 读取 @block 的字面量参数，不接受变量、函数调用或参数展开。修改文件任意内容都会影响摘要，包括注释；重新加载修改版时必须更新 version。

## 可以使用的函数与校验钩子

- 一个文件必须恰好有一个注册函数，可包含未装饰的辅助函数及多个模型。
- 普通块只接受一个无默认值的位置参数，参数和返回值都必须有类型注解；API 块另接收无默认值的关键字参数 `api: BlockAPI`。可另声明无默认值的关键字参数 `context: BlockContext`，通过 `context.file(reference)` 访问当前任务附件，通过 `context.model(name)` 获取声明模型路径，通过 `context.progress(message, current=..., total=...)` 报告实际进度。不支持 `*args`、`**kwargs` 或其他任意能力参数。
- `def run(value: Input) -> Output` 和 `async def run(value: Input) -> Output` 都可以。两者均在对应 Python 子进程中执行；CPU 计算不会占用平台事件循环，取消或超时会终止子进程。每次调用均创建新进程，不依赖模块全局变量跨调用保留状态。
- 模型可使用 Pydantic `field_validator`、`model_validator`；完整写法见 [契约示例](../contracts/README.md)。入口含自定义校验时，接线会受到契约身份限制。
- 没有 on_load、before_run、after_run、on_error、on_cancel 注册钩子。前后处理写在函数内；需要局部资源清理时使用 Python `try/finally`。

独立文件只快照自身源码，不能相对导入邻接自有文件。把自有类型和辅助函数一起放入文件。加载会导入顶层代码，因此顶层只放声明，不启动请求或修改外部状态。

API 块通过注入的 BlockAPI 向节点配置的路径发起请求，凭据由平台传输层管理；块不接收模型调用接口，模型交互使用业务包。普通异常会使步骤失败；如需明确的错误，使用平台已有错误码构造 `PlatformError(ErrorResponse(...))`，字段定义见 [错误契约](../../src/agent_platform/contracts/errors.py)。不要返回伪造成功值。

## 输入参数怎么固定

块的业务选项包含在输入契约中；`nodeConfigurations` 为 API 块保存连接引用和请求路径。第一步自动接收服务完整输入，后续步骤自动接收上一层完整输出，均须符合 Input 契约；需要固定选项或拼装字段时，先通过另一个通用块处理。例如完整块节点：

```json
{
  "nodeId": "normalize",
  "kind": "block",
  "artifactRef": "替换为加载完整块返回的 resourceId"
}
```

调用数据可包含 options，例如 {"query":"内容","options":{"letterCase":"upper"}}；其余选项由 Options 默认值补齐；服务输入的 query 仍须满足块的长度约束，并为 normalize 节点配置下方的 API 连接和请求路径。最容易成功的接法是直接选择此块返回的 inputContract/outputContract 作为服务端口，并采用完整输入/输出接线，见 [公共用法](../USAGE.md)。

## 完整块的 API 配置

[complete.py](complete.py) 声明 `@block(..., api=True)`，函数签名为 `async def normalize(value: Input, *, api: BlockAPI, context: BlockContext) -> Output`。最小示例保持无外部依赖的单输入计算函数。

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
5. 将块输出接入服务出口，或先通过另一个通用块提取 text、输出符合契约的完整对象，再接入最小 Prompt 包。完整包要求非空且不超过 10000 字符，须先通过明确验证该约束的转换块，因为整理结果可能为空，添加前缀后也可能超长。只有通用块时无需模型环境或模型预算。

完整示例通过以下调用使用平台节点的路径：

```python
response = await api.request('GET', {'query': value.query}, response_type=APIResponse)
```

`await api.request(method, payload, response_type=APIResponse)` 支持 GET/POST/PUT/PATCH/DELETE；GET 的 payload 为查询参数，其余为 JSON 请求体。节点的 api.path 是 Base URL 下的相对路径，不接受完整 URL、查询字符串或目录回退，不提供隐含默认路径。response_type 必填，响应经过严格校验后返回对应类型；具体响应外壳的解包由块代码完成。

例如 Base URL 为 `https://example.com/api`、节点 path 为 `/lookup`，请求地址为 `https://example.com/api/lookup`。另一个节点可复用同一完整块，把 path 配成 `/search`；接口须接受相同参数并返回符合 APIResponse 的数据。路径随实例快照保存，修改并保存后生成新实例版本，不改变已提交任务或历史版本。旧节点配置需补充 api.path；旧块调用需去掉 request 的路径参数。

平台固定任务使用的 API 环境，任务排队至结束期间禁止修改所引用环境。请求失败或超时直接报错；输出不满足契约时按服务 retryLimit 重试，次数耗尽后任务失败，错误不回显凭据和原始响应。取消在执行边界生效，应用退出关闭在途本地传输。重试会重新调用该通用块及其外部 API，不撤销已发生的外部操作。

## 文件与模型

完整示例的可选 `attachment: TaskFile | None` 会在任务页生成 PDF/DOCX 控件。保存完成后平台自动补入引用；手写本机路径不能替代文件上传。示例检查附件可用性并用 with 只读前 16 字节，未实现文档解析或 OCR。其他业务字段仍填写 JSON。

下载声明的准确字段、来源约束、缓存和超时说明见 [平台运行文件与依赖](../../docs/platform-runtime-files.md)。完整模板的依赖来源、模型清单为空，因此加载模板不会触发第三方包安装或模型下载。需要模型的块必须填写经过核验的真实地址与摘要，并把 `context.model(name)` 返回的路径显式传给推理库，禁止在任务函数中安装包或隐式下载模型。

## 进度与教学边界

完整块实际调用 `context.progress`：附件检查和 API 等待阶段只发送消息；API 响应校验后上报 `1 / 3`，文本整理后上报 `2 / 3`，输出构造成功后上报 `3 / 3`。任务页按相同通用协议显示，不需要针对块另写前端适配。API 或业务校验失败时不会报告后续阶段完成。

进度不是输出，也不是完整日志：平台保存步骤的最新进度，页面不保证展示每条短暂消息；`3 / 3` 仅表示块内处理完成，平台还会校验出口并运行后续节点。不能用 progress 代替逐框 OCR 诊断、审计事件或任务成功状态。

Input 使用 `field_validator` 演示纯空白查询校验。此校验无法完全表达为 JSON Schema，服务开始端口优先选本块导出的 inputContract；与其他类型接线时仍以平台校验为准。源码说明了 model_validator 的适用场景、同步/异步入口、模型路径接入、全部装饰器参数、资源清理及取消/重试边界；没有声明或实现额外生命周期钩子。

本次教学示例验证使用已有依赖与临时本地 HTTP 服务：静态声明、严格输入、实际块子进程/API/附件调用、输出契约、成功进度、空白正文失败与非法 API 响应均通过。测试资料与运行缓存已清理；没有安装新依赖、调用线上模型或进行完整桌面人工验收。
