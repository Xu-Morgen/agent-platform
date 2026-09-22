# 外部资源研发手册：输入、注入与平台能力

适用基线：2026-09-21，执行协议 **flow-6**，Python 3.12+。本文面向编写通用块、Prompt 业务包和独立契约的开发者，说明平台实际向资源提供什么、如何声明、如何配置及如何调用。示例以当前仓库实现为准；平台尚未提供独立发布的第三方 SDK 安装流程，资源在平台准备的 Python 环境中导入 `agent_platform`。

资源卡片现已展示逐位置参考数量、类型和用途；开发者通过模型文档字符串、`Field(description=...)` 和固定元组位置上的 `Annotated` 补充说明，具体见 [资源用途说明](resource-explanation.md)。说明变化也需递增包/块版本，已有实例不会自动升级。

## 1. 能力总表

这里的“注入”包括函数参数注入、节点数据装配和 Prompt 替换。它们使用不同入口，不能互换。

| 能力 | 使用方 | 声明或接收方式 | 使用方法 | 配置位置 |
| --- | --- | --- | --- | --- |
| 主数据 | 块、包 | `NodeInput[P, R]` 中的 `primary` | 块读 `value.primary`；包用 `{{input.primary}}` | 服务输入及前一步完整输出，平台自动装配 |
| 有序参考数据 | 块、包 | `R` 为固定位置元组 | 块读 `value.references[0]`；包用 `{{input.references[0]}}` | 节点简单/高级参考设置 |
| 外部 JSON API | 通用块 | `@block(api=True)` 与 `*, api: BlockAPI` | `await api.request(...)` | 环境页 API 连接；节点连接选择与 `api.path` |
| 任务文件访问 | 通用块 | 输入字段 `TaskFile`；`*, context: BlockContext` | `context.file(reference)` 返回 `pathlib.Path` | 任务页上传，或文件上传接口 |
| 本地图片 OCR | 通用块 | `@block(ocr=True)`；异步 `context` | `ocr` | 平台管理模型组合并在提交时固定，见 [OCR 接口](local-ocr.md) |
| 任务内本地语义检索 | 通用块 | `@block(semanticSearch=True)`；异步 `context` | `semantic_split` / `semantic_search` | 平台设置默认模型在提交时固定，见 [接口](local-embedding-contracts.md) |
| 已准备的本地模型文件 | 通用块 | `@block(models=[...])`；`context` | `context.model(name)` 返回 `Path` | 块的静态模型声明 |
| 步骤进度 | 通用块 | `context` | `context.progress(message, current=..., total=...)` | 无需额外节点配置 |
| 业务参数及默认值 | Prompt 包 | `contractRefs.configuration` 指向 Config | `{{parameters.xxx}}` | 包节点 `parameters` |
| LLM 调用 | Prompt 包 | 输入/输出契约及 Prompt | 平台渲染 Prompt 后统一调用 | 包节点 `model`、`maxOutputTokens`、预算 |
| 第三方 Python 库 | 通用块 | `dependencies`、`dependencySources` | 运行时普通 `import` | 静态声明，由平台准备独立环境 |
| 独立契约 | 服务端口 | 导出的严格类型及 symbol | 加载后用于端口和兼容检查 | 服务输入、输出等契约选择 |

**通用块公开的额外函数参数只有 `api`、`context`。** `NodeInput` 是业务数据参数；依赖是环境准备；包参数是 Prompt 数据。独立契约不接收运行上下文。不要把平台内部的 RuntimeContext、数据库对象或 LangGraph 状态视为资源 SDK。

## 2. 通用块的合法函数签名

```python
from agent_platform.blocks import block, BlockAPI, BlockContext
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput
```

单个 `.py` 文件必须恰有一个顶层 `@block` 注册函数。第一个参数名称可以自行选择，但必须无默认值、声明 `NodeInput` 类型，并声明返回类型。以下为签名示意，`Input`、`Output` 需在实际文件中定义：

```python
# 普通计算；也允许 async def。
def run(value: NodeInput[Input, tuple[()]]) -> Output: ...

# 可选上下文，不要求 api=True；同步/异步均可。
def run(value: NodeInput[Input, tuple[()]], *, context: BlockContext) -> Output: ...

# API 必须使用 async def，并在装饰器中声明 api=True。
async def run(value: NodeInput[Input, tuple[()]], *, api: BlockAPI) -> Output: ...

# 同时使用两种能力。
async def run(value: NodeInput[Input, tuple[()]], *, api: BlockAPI,
              context: BlockContext) -> Output: ...
```

`api`、`context` 必须使用上述名称、准确的类型注解、关键字专用参数，并且无默认值。不能写 `context=None`、`**kwargs` 或增加 `db`、`logger`、`config` 等参数。无需自行实例化 `BlockAPI` 或 `BlockContext`；平台执行时提供实现，子进程内可能是代理对象，应依赖公开方法，不做具体实现类判断或读取私有属性。

装饰器所有参数必须为字面量，不能使用变量、函数调用或 `**kwargs`。加载时会静态检查声明、准备环境，再导入与检查函数。不要在模块顶层执行网络请求或业务操作；导入与契约校验也可能发生在独立进程中。

## 3. 主数据与参考如何进入资源

### 3.1 类型声明

```python
class Text(StrictModel):
    text: str

class Rules(StrictModel):
    prefix: str

# 零参考：NodeInput[Text, tuple[()]]
# 一个参考：NodeInput[Text, tuple[Rules]]
# 两个参考：NodeInput[Text, tuple[Rules, Text]]
```

`references` 必须固定数量、位置和类型，不支持 `tuple[T, ...]`。JSON 数组会转成元组，但元素仍严格校验。字段模型继承 `StrictModel`，拒绝未知字段与隐式类型转换；Python 的 `source_text` 在公开 JSON 和 Prompt 路径中使用 `sourceText`。

服务调用者只交业务 JSON，例如 `{"text":"hello"}`。首节点实际收到 `{"primary":{"text":"hello"},"references":[]}`。后续普通节点的 `primary` 自动接收上一层的**完整输出**；节点不能自行选择主数据来源、裁剪字段或改名，需要转换时插入通用块。

### 3.2 默认参考不是上一节点输出

设节点 A 的主数据是 X，输出是 Y，则其后节点 B 收到 `primary=Y`，简单模式下 `references=(X,)`。不会把 A 的整份 `NodeInput` 或 A 的旧 references 递归带入。

| 位置 | 主数据 | 简单模式参考 |
| --- | --- | --- |
| 服务第一步 | 完整服务输入 | 空 |
| 普通后续节点 | 上一步完整输出 | 上一步当次 primary，恰一项 |
| if 条件及分支首节点 | 进入 if 的主数据 | 继承进入 if 的默认参考 |
| while 条件、while/repeat 循环体首节点 | 当前 carry | 空 |
| 容器之后 | 容器完整输出 | 容器入口主数据；循环为初始 carry |

因此零参考资源放在普通后续位置时，必须选高级模式并设空列表 `[]`。高级参考会**替换**默认列表，不能与默认列表自动合并。

以下仅为节点片段，`artifactRef` 必须替换为已加载资源 ID：

```json
{
  "nodeId": "combine",
  "kind": "block",
  "artifactRef": "replace-resource-id",
  "references": [
    {"kind": "input"},
    {"kind": "node", "nodeId": "prepareRules"}
  ]
}
```

此时槽位 0 是完整服务输入，槽位 1 是可见的 `prepareRules` 完整输出。支持 `input`、前序可见 `node`、当前循环 `carry`（需填循环 nodeId）；禁止重复、前向、越域及上一轮残留结果。常量和字段路径不能作为高级参考来源。

if/while 条件仍是普通通用块，使用相同注入方式，但返回类型必须是严格 `bool`，不能返回 `1` 或 `{"result":true}`；条件不替换业务主数据。完整容器设置见 [加载与接线](../samples/USAGE.md#控制容器字段)。

## 4. context：文件、本地模型、进度

### 4.1 可直接加载的文件块

把下列内容保存为一个 Python 文件，在服务页加载，输入选该块的“主数据输入”契约，输出选其输出契约，并将它作为第一步。此示例不需要额外依赖或外部连接。

```python
from agent_platform.blocks import block, BlockContext
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.files import TaskFile
from agent_platform.contracts.node_input import NodeInput

class Input(StrictModel):
    document: TaskFile

class Output(StrictModel):
    size: int

@block(id='external-file-size', version='1.0.0', name='读取任务文件大小')
def run(value: NodeInput[Input, tuple[()]], *, context: BlockContext) -> Output:
    context.progress('检查任务文件')
    path = context.file(value.primary.document)
    size = path.stat().st_size
    context.progress('文件检查完成', current=1, total=1)
    return Output(size=size)
```

`TaskFile` 是带 Schema 标注的文件引用，支持 PDF/DOCX。任务页上传后平台产生 `fileId`、`originalName`、`format`、`size`、`sha256`，业务数据不传本机路径。API 调用者先请求 `POST /api/v1/files?name=example.pdf`，请求体为原始文件流，再把响应中的文件引用放入 `document` 字段提交任务。

`context.file(reference)` 只能解析当前任务关联的有效引用。平台检查归属和副本完整性，返回平台保存的副本路径；源文件移动不影响该副本。按只读约定使用，文件格式及业务可读性仍由解析块检查。它不是任意文件路径解析器，也没有对应的 `context.save_file()` 输出接口。引用缺失或无权关联当前任务时明确失败；文件上传限制和保留策略见 [运行文件说明](platform-runtime-files.md#文件输入与受控上下文)。

### 4.2 本地模型路径

模型文件在块加载/准备阶段声明并下载，业务函数只消费已准备的路径。`models` 每项字段如下：

| 字段 | 含义 |
| --- | --- |
| `name` | 块内访问名，以英文字母开头，仅字母、数字、下划线、连字符 |
| `version` | 模型版本标识 |
| `url` | 固定 HTTPS 地址，不含凭据、查询参数或 fragment |
| `sha256` | 发布文件实际的 64 位小写 SHA-256 |
| `filename` | 单个文件名，不能包含目录 |

声明是真实文件时，在带 `context` 的函数内使用：

```python
model_path = context.model('fixedModel')  # 必须与 models 中的 name 一致
# 将 str(model_path) 显式传给实际推理库的模型路径参数。
```

这里展示调用片段，不提供虚构下载地址或摘要。模板默认 `models=[]`，此时调用任何模型名称都会失败。每个声明对应一个文件，平台不自动解压；需要多个文件就分别声明。`context.model()` **不执行推理，也不是 LLM 客户端**。推理库通过 dependencies 声明，禁止在任务函数中调用 pip、依赖库隐式下载或改写缓存。未声明或未就绪名称报 `DEPENDENCY_ERROR`。

### 4.3 进度

```python
context.progress('等待外部响应')
context.progress('处理页面', current=3, total=10)
```

方法为同步调用，不使用 `await`。无确定总量时只报消息；有总量时按实际完成量上报。平台把最新事件写入当前步骤的 `progress`，可在任务详情或 `GET /api/v1/runs/{runId}` 查看。它不追加到业务输出，也不是完整日志流，`10/10` 不代表整个任务成功。`print()` 不是公开日志接口，当前子进程打印不会作为任务日志保存。

## 5. api：绑定连接的 JSON 请求

### 5.1 代码声明与调用

```python
from agent_platform.blocks import block, BlockAPI
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput

class Input(StrictModel):
    query: str

class Response(StrictModel):
    text: str

@block(id='external-lookup', version='1.0.0', name='查询外部文本', api=True)
async def run(value: NodeInput[Input, tuple[()]], *, api: BlockAPI) -> Response:
    return await api.request(
        'GET', {'query': value.primary.query}, response_type=Response,
    )
```

以上是完整单文件示例，但执行前必须有真实匹配的 API 服务及连接配置。响应必须符合 `Response`；外部接口返回包裹结构时，先声明真实响应契约，再用块代码转换成出口契约。

### 5.2 在页面绑定什么

1. 环境页创建 API 连接，填写 Base URL、可选凭据和超时。
2. 服务页加载该块，为节点选择 API 环境及连接，填写请求路径。
3. 设置端口、参考与其他步骤，校验并保存实例后提交任务。

例如节点 ID 为 `lookup`，下面是 FlowDraft 的配置片段，不是完整服务请求：

```json
{
  "nodeConfigurations": {
    "lookup": {
      "api": {
        "environmentId": "replace-environment-id",
        "connectionId": "lookup-api",
        "path": "/lookup"
      }
    }
  }
}
```

若 Base URL 为 `https://example.com/api`，最终地址是 `https://example.com/api/lookup`。`path` 相对于该 Base URL，允许前导 `/`，不允许完整 URL、查询串、fragment 或目录回退。查询条件放 GET payload，不放 path。块代码不传 path；修改节点路径后保存新实例版本。

### 5.3 请求接口与限制

公开签名为 `await api.request(method, payload=None, *, response_type)`：

| 项目 | 当前行为 |
| --- | --- |
| method | 大写 `GET`、`POST`、`PUT`、`PATCH`、`DELETE` |
| payload | 可 JSON 序列化的数据；GET 为查询参数，其他方法为 JSON body |
| response_type | 必填，平台支持的严格类型；返回前运行时严格校验 |
| 返回值 | 按 response_type 校验后的值；模型类型可直接读属性 |
| 路径与连接 | 一个节点绑定一条 API 连接及一个路径；同一入口内多次请求仍使用同一绑定 |
| 认证 | 平台有凭据时发送 `Authorization: Bearer ...`；凭据不注入业务子进程 |
| 超时 | 来自环境连接的 timeoutSeconds |
| 响应形式 | 成功 HTTP 响应仍必须是 JSON；不提供原始 Response 或响应头 |

当前接口没有自定义 headers、cookies、multipart、流式下载、动态路径或多连接选择参数；不自动跟随重定向。请求 payload 不会自动依据块输入 Schema 再生成独立请求契约，开发者应从已校验输入构造符合目标接口的数据；`response_type` 则明确承担响应校验。需要多个固定路径时拆为多个节点并分别绑定。

传输失败、超时、非 JSON 或响应类型错误会明确失败。不要吞掉异常返回空结果；服务契约重试可能再次执行整个块，外部写操作不会回滚，也没有平台自动去重保证。

## 6. Prompt 包：输入与参数替换

包只交付契约、参数和 Prompt，不接收 `api`、`context`，也不编写 `invoke()`。最小目录为 `package.json`、`models.py`、`prompt.txt`。

以下三个文件组成一个带业务参数的最小包，入口零参考：

`models.py`：

```python
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput

class Text(StrictModel):
    text: str

class Entry(NodeInput[Text, tuple[()]]):
    pass

class Config(StrictModel):
    language: str = '中文'
```

`package.json`：

```json
{
  "packageId": "external-summary",
  "version": "1.0.0",
  "name": "文本摘要",
  "contractRefs": {
    "input": "models:Entry",
    "output": "models:Text",
    "configuration": "models:Config"
  },
  "prompt": "prompt.txt"
}
```

`prompt.txt`：

```text
请用 {{parameters.language}} 概括以下文本，并按平台要求返回 JSON：
{{input.primary.text}}
```

页面加载包目录后，配置 `parameters`（例如 `{"language":"英文"}`）、模型环境与连接、节点预算、任务预算和 `maxOutputTokens`。省略 language 使用 Config 默认值；同包不同节点的参数独立。无 configuration 契约时，参数只能是空对象。

| 占位符 | 获取内容 |
| --- | --- |
| `{{input}}` | 整份已校验 NodeInput，包含 primary/references |
| `{{input.primary.text}}` | 主数据字段 |
| `{{input.references[0].text}}` | 声明了对应参考槽时，取该槽字段 |
| `{{parameters}}` | 校验并补全默认值后的业务参数 |
| `{{parameters.language}}` | 单个参数 |

字符串原样插入，其他值按 JSON 序列化；仅替换一次，不再次解析输入中的占位符。只支持契约可验证的对象字段和固定元组索引，不支持表达式、函数、过滤器、条件模板或动态列表索引。可空/联合类型内部字段不能直接访问，可插入整个值或先用块转换。

只有 Prompt 明确引用的数据会发送给模型；声明参考不等于自动发送参考。文件引用也不会自动变成文件正文，先通过读取块提取文本。API 查询同样由上游块完成。

平台在系统消息中附输出 JSON Schema，并发送渲染后的用户消息；模型连接、密钥、预算不进入 `parameters`，也没有 `{{environment}}`、`{{secrets}}` 或 `{{runId}}` 占位符。模型实际用量由任务记录提供，不混入业务输出。详见 [包执行入口](../samples/packages/CONTEXT.md) 和 [完整配置](../samples/packages/CONFIGURATION.md)。

## 7. 第三方依赖与运行生命周期

`dependencies` 为带版本约束的 PEP 508 列表，正式交付使用已验证的固定版本；标准库、平台 SDK 和内置 Pydantic 不必声明。`dependencySources` 支持单一 HTTPS 索引或带真实 SHA-256 的 wheel 来源；wheel 包必须在 dependencies 中声明。块为单文件快照，不能相对导入旁边未快照的自有源码。包不声明运行依赖。

平台先锁定 wheel 及传递依赖，再准备独立环境与模型缓存；不支持源码构建、安装脚本或系统库自动安装。准备过程可能联网下载，与任务运行及包 loop 分开。完整字段和缓存恢复机制见 [运行文件与依赖](platform-runtime-files.md#静态声明)。

每次块调用使用新子进程，单次业务执行上限当前为 300 秒。不要依赖模块全局变量保存跨调用状态；循环业务状态使用 carry，跨节点数据通过明确契约传递。纯计算取消可以终止子进程；进行中的 API 请求沿用平台传输取消边界。强制退出不保证执行 `finally`，不承诺撤销已完成的外部操作。

当前没有 `on_load`、`before_run`、`after_run`、`on_error`、`on_cancel` 等资源钩子。前后处理写在块入口中，普通文件句柄用 `with`，可正常释放的资源用 `try/finally`。平台统一管理任务终态与取消，不向资源注入可修改的流程、预算管理器或持久化检查点。

资源按受信任本地代码运行。子进程隔离用于环境和生命周期管理，不等于权限沙箱。本文的“只读路径”是使用约定，不表示操作系统阻止修改。

## 8. 错误、验证与发布

业务无法完成时可以抛平台明确错误，不应把错误消息装进成功结果：

```python
from agent_platform.contracts.errors import ErrorResponse, PlatformError

# 放在实际业务检查分支内。
raise PlatformError(ErrorResponse(
    code='CONTRACT_VALIDATION_ERROR',
    stage='block.external_lookup',
    message='查询条件不满足业务要求',
    field_path=['primary', 'query'],
))
```

错误码使用 [公开错误契约](../src/agent_platform/contracts/errors.py) 已定义的值，不自创代码；消息不得包含认证信息或完整敏感响应。一般 Python 异常可能被归为 `BLOCK_PROCESS_ERROR`，需要对用户说明的业务失败应使用明确平台错误。

| 现象 | 优先检查 |
| --- | --- |
| 资源加载报配置错误 | 装饰器是否为字面量、是否只有一个注册函数、签名/注解是否正确 |
| 参考数量或类型不匹配 | 零参考后续节点是否设 `[]`；槽位是否按顺序匹配完整来源 |
| 文件访问失败 | 是否使用上传结果、已绑定当前任务且副本有效，是否误传本机路径 |
| 模型文件未就绪 | models 中的 name、实际 URL/摘要以及准备阶段错误 |
| API 块无法保存/运行 | api=True、异步入口、api 注解、环境连接和 api.path 是否齐全 |
| 输出契约失败 | 返回业务结构是否匹配；外部响应是否有未声明字段或响应外壳 |
| Prompt 加载失败 | JSON 字段名、声明参考槽及占位符路径是否有效 |
| 同版本导入冲突 | 内容改变后是否递增块/包 version，包括注释变化 |

静态不兼容会阻止保存；运行时输入错误阻止消费者执行。输出契约错误按服务 `retryLimit` 重试相应生产者，默认额外 3 次；参考缺失、参考校验及消费者跨字段错误不会重跑无关历史生产者。传输或业务失败不应当作通用自动重试机制使用。包每次尝试均计 loop，token 按供应商实际用量累计。

建议按以下顺序完成外部资源交付：

1. 从 [三类模板](../samples/README.md) 选择资源，固定输入、参考、输出和参数契约。
2. 只声明需要的注入，先用无外部依赖的小输入验证加载、接线和业务输出。
3. 涉及 API、文件或模型时，补齐真实环境和准备条件，验证一次成功与必要失败边界；替身不能代替真实模型验收。
4. 通过服务页加载、配置、校验并保存实例，使用任务页或稳定服务 API 调用；不交付只为单个实例自动组装服务的脚本。
5. 修改源码后递增块/包版本，重新导入、替换草稿资源并保存新实例；历史实例和已提交任务仍使用原快照。配置变化也需保存实例。
6. 交付资源源码、兼容依赖、输入示例和操作说明，清理临时测试与数据，记录实际通过及尚未完成的验证。

稳定服务的任务提交、状态查询和取消 API 见 [保存与外部调用](../samples/USAGE.md#5-保存版本与外部调用)。业务参数、源码或资源导入不能直接修改已有任务。

## 9. 当前没有开放的注入

| 需求 | 当前处理方式 |
| --- | --- |
| 直接获取平台 PostgreSQL、repository、事务或主密钥 | 无资源注入接口；平台存储由桌面内部管理 |
| 本地知识库与最小 RAG | 已提供 TaskKnowledge、BlockContext 异步受控读取与证据登记；算法由普通资源实现，见[开发接口](knowledge-api.md) |
| 业务数据库连接、向量库、工具注册表 | 尚未提供统一注入能力；已有外部 JSON 服务可用 API 块对接 |
| 块内获取 LLM client、模型凭据或 PackageContext | 不提供；模型交互通过 Prompt 包节点 |
| logger、任意事件总线、artifact 写入接口 | 不提供；步骤进度使用 context.progress，业务结果通过出口 |
| runId、nodeId、全局任务对象、可修改预算或取消 token | 不提供公开资源参数；需要业务标识时在契约中明确传入 |
| 自动执行模型返回的代码或流程 | 不支持；模型输出必须通过固定契约，条件由 Python 块判断 |

不要通过导入内部模块、读取私有属性或环境变量绕过这些边界。需要未开放能力时应明确新增平台接口及契约，再更新手册，不能仅在资源中约定一个不存在的参数。

## 10. 实现依据与相关入口

- [块签名与注入校验](../src/agent_platform/registry/single_blocks.py)、[块公共导出](../src/agent_platform/blocks/__init__.py)。
- [BlockContext](../src/agent_platform/blocks/context.py)、[BlockAPI](../src/agent_platform/blocks/api.py)、[子进程代理](../src/agent_platform/blocks/worker.py)。
- [节点输入](../src/agent_platform/contracts/node_input.py)、[文件引用](../src/agent_platform/contracts/files.py)、[依赖和模型声明](../src/agent_platform/contracts/dependencies.py)。
- [节点配置与参考结构](../src/agent_platform/contracts/flows.py)、[Prompt 替换与调用](../src/agent_platform/runtime/packages.py)。
- [包含 API、附件及进度的完整块](../samples/blocks/complete.py)、[完整 Prompt 包](../samples/packages/complete/README.md)、[独立契约开发](../samples/contracts/README.md)。

本文交付的是当前能力的研发说明，没有新增注入接口或改变运行协议。


## 知识库访问

输入字段使用 `TaskKnowledge`，平台在提交时固定当前修订；只在已绑定范围调用：

```python
from agent_platform.contracts.knowledge import TaskKnowledge, KnowledgePageRequest

# 函数依然只声明 *, context: BlockContext；业务输入不携带平台路径。
reference = await context.knowledge_resolve(value.primary.knowledge)
page = await context.knowledge_list(KnowledgePageRequest(reference=reference, limit=20))
```

异步方法、严格契约、上限和错误详见[知识库 API](knowledge-api.md)，可替换的完整资源见[默认 RAG](../resources/rag/README.md)。证据正文摘要和候选/选用关系在登记接口检查，最终回答及引用关系通过明确的核验块检查；这些关系不能依靠结构 Schema 推断为成立。自定义资源必须保留明确错误、准确扫描范围及自身解析身份，不直接访问平台数据库或私有原件目录。
