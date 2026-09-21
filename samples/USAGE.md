# 加载、接线和调用模板

以下命令在仓库根目录执行，使用现有 `.venv` 依赖。桌面可按主 README 启动；也可先在独立终端运行 API：

```bash
.venv/bin/python -m agent_platform --host 127.0.0.1 --port 8000
```

API 文档在 `http://127.0.0.1:8000/docs`。桌面显示的后端地址可能不是 8000；两次启动是独立会话，资源 ID、环境和任务不能跨会话复用。

## 1. 三种加载请求

统一 `POST /api/v1/catalog/load`：

```json
{"kind":"block","path":"/absolute/path/samples/blocks/minimal.py"}
```

```json
{"kind":"package","path":"/absolute/path/samples/packages/minimal"}
```

```json
{"kind":"contract","path":"/absolute/path/samples/contracts/minimal.py","symbol":"Text"}
```

| 字段 | 作用 |
| --- | --- |
| kind | block/package/contract，决定加载方式 |
| path | 后端可读路径；块/契约选文件，包选目录；推荐绝对路径 |
| symbol | 契约必填，为文件中导出的类型名称；块/包省略 |

块/包返回 resourceId、primaryContract、inputContract、outputContract 和 schemas；primaryContract 是业务主数据契约，inputContract 是平台使用的完整 NodeInput 契约；包另有 configurationContract、budgetDefaults。API 块另有 apiRequired=true，需要在节点上配置 API 连接和请求路径 api.path。独立契约直接用 resourceId 作为端口引用，schemas.value 展示类型。

## 2. 可直接执行的最小闭环

通过服务页完成资源加载、拼接和保存，不使用自动组装服务的辅助脚本：

1. 加载 `samples/blocks/minimal.py`，再加载 `samples/contracts/minimal.py`，symbol 选 Text。
2. 新建服务，输入和输出均选择独立 Text 契约；也可分别选择最小块的“主数据输入”和“输出”契约。
3. 添加一个最小块，命名为 trim，保持简单参考模式。首节点默认没有参考，符合模板声明。
4. 校验后保存实例，在任务页提交 `{"text":"  hello  "}`，结果应为 `{"text":"hello"}`。
5. 若添加第二个最小块，把第二个块切换为高级参考模式，保持空列表；该模板声明零参考，默认的一项参考会被严格拒绝。

服务调用方只提交业务 JSON。平台实际给首块的输入是 `{"primary":{"text":"  hello  "},"references":[]}`；最终返回仍是业务结果。

## 3. 包与 API 通用块如何组成服务

在服务页添加最小 package 节点，nodeId 设为 summarize；服务端口选该包的 primaryContract/outputContract。完整包声明一个参考，单独作为首节点时需使用高级模式，把 references[0] 绑定为服务输入。

在同一 FlowDraft 顶层加入：

```json
{
  "nodeConfigurations": {
    "summarize": {
      "parameters": {},
      "budget": {"loopLimit": 4, "tokenLimit": 32768},
      "model": {"environmentId": "replace-environment-id", "connectionId": "replace-model-connection-id"},
      "maxOutputTokens": 512
    }
  },
  "budget": {"loopLimit": 4, "tokenLimit": 32768}
}
```

这是待合并的配置片段，替换实际 ID 后再发送；不是完整保存服务请求。完整包则使用其 [节点配置示例](packages/complete/node-configuration.example.json)。包的创建步骤见 [packages/README.md](packages/README.md)。

### 最完整通用块的节点配置

加载 `samples/blocks/complete.py`，使用其 primaryContract/outputContract 作为服务端口，将块节点命名为 normalize，并将服务完整输入传给块节点，平台自动返回该节点的完整输出。在同一 FlowDraft 顶层加入：

```json
{
  "nodeConfigurations": {
    "normalize": {
      "api": {
        "environmentId": "replace-environment-id",
        "connectionId": "lookup",
        "path": "/lookup"
      }
    }
  }
}
```

替换为实际 API 环境和连接 ID；path 必填，为该连接 Base URL 下的请求路径。环境保存 Base URL、凭据和超时，节点保存路径；方法、请求参数和响应契约由块定义。该片段不是完整的服务保存请求。只有通用块时不需要模型连接或任务预算。

输入示例为 `{"query":"greeting"}`（query 不能全为空白），可另带 options 和可选任务附件；`options.requireContent=true` 时拒绝整理后为空白的正文。块使用 `api.request('GET', {'query': value.primary.query}, response_type=APIResponse)`，请求节点配置的路径。若 Base URL 是 `https://example.com/api`，实际请求为 `https://example.com/api/lookup?query=greeting`；这是配置示意，项目不提供此远端服务。响应要求及选项见 [完整块说明](blocks/README.md#最完整实现)。

完整块会上报 API 等待消息及三个处理阶段的实际进度；进度不加入业务输出，不代表整个任务成功。

修改路径后保存实例版本即可生效，无需修改块源码；已提交任务继续使用原路径，历史回退恢复历史节点路径。旧 API 节点配置需补充 api.path，旧块的 api.request 调用需移除路径参数。

## 4. FlowDraft 的公共配置

| 字段 | 必填/默认 | 作用 |
| --- | --- | --- |
| draftId | 可省略 | 可选草稿标记，不是可调用的 serviceId |
| name | 必填，非空 | 流程名称 |
| inputContract / outputContract | 必填 | 已加载的服务端口契约引用 |
| flow | 必填列表 | 顺序执行的节点及控制容器 |
| retryLimit | 默认 3，整数 0～1000 | 运行时输出不符合契约时的最大额外重试次数；0 表示不重试，声明类型不兼容直接拒绝保存 |
| nodeConfigurations | 默认 {} | 按 nodeId 保存包的模型配置或 API 通用块的连接与请求路径配置；普通计算块和控制容器无需配置 |
| budget | 默认 null；含包必填 | 全局 loop/token 累计限额 |
| examples | 默认 [] | 每项 `{name, input}`，示例输入供界面使用，不是自动测试或自动执行 |

### 块/包节点

| 字段 | 作用 |
| --- | --- |
| nodeId | 整个流程内唯一，以英文字母开头，仅字母/数字/下划线/连字符 |
| kind | block/package |
| artifactRef | 对应加载结果 resourceId |
| references | 省略或 null 为简单模式；数组为高级模式并替换默认列表，允许 []；每项仅含 kind 与可选 nodeId，禁止重复 |

### 分支与循环的数据来源

| 字段 | 作用 |
| --- | --- |
| source.kind=input | 引用服务输入，不填 nodeId |
| source.kind=node | 引用可见前序节点输出，必须填 nodeId |
| source.kind=carry | 引用循环当前携带值，nodeId 填循环节点 ID |
| source.kind=constant | 直接填符合接收方契约的完整 value，不填 nodeId/path |

资源入口统一声明 `NodeInput[P, R]`，P 为主数据契约，R 是固定位置元组；JSON 为 `{primary, references: [...]}`。服务第一步 primary 为完整服务输入，后续为上一层完整输出。简单模式的 references 只有上一节点此次的 primary，首节点为零项，不递归保留参考。高级模式按声明的槽位选择完整服务输入、已执行且可见节点的完整输出或当前 carry；顺序、数量、类型均校验，不能重复、前向或越域引用。

if 条件与分支首节点都收到进入 if 的主数据及同样的默认参考。while 条件和循环体首节点、repeat 循环体首节点默认零参考，以当前 carry 为 primary。内部第二步起按普通顺序规则。容器后的默认参考为容器入口主数据，循环为初始 carry；不得读取上一轮节点残留结果。

平台不支持字段路径引用、改名或拼装；需要转换时添加通用块。常量仅允许用于控制容器的完整值绑定，不能作为高级参考。服务返回仅配置 outputContract，自动返回顶层最后一步完整输出；空流程不能保存。API 的请求路径 api.path 不受节点输入封装影响，块通过 value.primary 生成业务请求并单独校验业务响应。

主数据字段错误尽可能在直接生产节点输出检查时识别，按 retryLimit 重试该生产节点；参考缺失、参考校验与消费者跨字段错误立即失败，不重跑历史生产者。任何输入错误都会阻止消费者执行。条件输出错误可重试条件块，不执行错误分支；外部副作用不回滚。

### 控制容器字段

| kind | 配置 | 语义 |
| --- | --- | --- |
| if | nodeId、condition、outputContract、thenBranch、elseBranch | condition 是 kind=block 的完整节点，独立执行并返回严格 bool；两条分支均有 nodes（默认 []）和必填 output 接线，共用出口契约 |
| repeat | nodeId、count、carry、body | count 为非负整数；body 默认 []；0 次返回初始 carry |
| while | nodeId、maxIterations、condition、carry、body | condition 是一个 kind=block 的完整节点，输出严格 bool；body 默认 []；maxIterations 是正整数 |
| foreach | nodeId、source、arrayPath、maxItems、itemOutputContract、body | 完整来源中选择数组；逐项独立执行非空 body，返回派生 items 集合 |
| switch | nodeId、router、outputContract、cases | router 为有限字符串 Literal 出口的 Python 块；cases 完整覆盖枚举，单次执行一个分支 |
| carry | contract、initial、update | 携带值类型、初始接线、每轮结束更新接线，三项均必填 |

if.condition 与 while.condition 使用相同的完整块节点格式；其 nodeId 也必须全局唯一，可以单独配置 references。while 达到上限后条件仍为真会失败。循环体以 carry 读当前状态；外部从容器节点出口读取结果，不能越过作用域读取内部节点。这些是服务编排字段，不是资源或包生命周期钩子。

foreach/switch 页面配置、作用域与可复制的教学资源源码见[数组遍历与枚举分支手册](../docs/control-flow.md)。`item` 完整来源指向可见 foreach 的当前元素，不支持更新；普通节点不开放字段映射。

## 5. 保存、版本与外部调用

| 操作 | API 与请求体 |
| --- | --- |
| 保存草稿 | POST /api/v1/drafts，`{content: FlowDraft}`；允许未完成内容 |
| 预检 | POST /api/v1/flows/validate，`{content: FlowDraft}`；检查返回 valid/issues |
| 创建稳定服务 | POST /api/v1/services，`{name, flow: FlowDraft}` |
| 保存新实例版本 | POST /api/v1/services/{serviceId}/versions，同上 |
| 获取业务契约 | GET /api/v1/services/{serviceId}/schema |
| 提交任务 | POST /api/v1/runs，`{serviceId, input}`；可带 expectedInstanceId |
| 查询状态/结果 | GET /api/v1/runs/{runId}；GET /api/v1/runs/{runId}/result |
| 取消任务 | POST /api/v1/runs/{runId}/cancel |

任务执行记录与包用量显示“业务包或通用块名称（node_x）”，分支和循环内的条件块也显示名称；历史任务按自身实例解析名称，不使用当前服务版本替换。

草稿不可直接调用；保存实例成功后稳定服务入口立即指向新版本。已提交任务固定代码、配置及实际环境。更新/退出语义和内存存储边界见 [项目说明](../readme.md)。

更新示例包或通用块源码时递增声明版本，再从页面导入。同一类型、同一 ID 的较低版本会自动归档，补导入旧版也默认归档；可在“管理资源 · 归档 / 恢复”中恢复。重复导入相同资源保留当前状态，独立契约仍手动归档。归档不影响已有草稿、实例和任务；要让服务使用新版，须替换草稿中的节点并保存新实例。

## 文件输入与运行环境

任务输入契约使用 `TaskFile` 的字段会显示 PDF/DOCX 选择控件；先保存文件，再提交任务，其他字段继续使用 JSON。任务文件副本与任务记录绑定，源文件移动不会影响任务；未提交上传保留 24 小时，历史任务附件保留到显式管理。

加载通用块会先静态读取 `@block` 字面量声明，再锁定依赖、准备独立环境和模型缓存，最后在对应 Python 子进程中导入与校验。页面显示实际阶段、来源和下载字节，可取消并重新加载重试；此准备不计业务 loop。完整模板仍使用空依赖及空模型清单，无需 OCR 下载。规范见 [平台运行文件与依赖](../docs/platform-runtime-files.md)。

## 文档业务组合

独立的 [文档出题实例](../examples/document-question-generation/README.md) 演示 PDF/DOCX 上传、本地 OCR、整份资料规划、独立审题和最多两轮修订，不改变本目录三类模板的用途。成功结果只包含通过最终验收的题目及依据；资料不足、引用无效或修订达到上限明确失败。题目结构错误按 retryLimit 重试生产包，业务修订与技术重试分开计数，全文不静默截断。

## 升级旧协议

flow-6 不执行 flow-5 及更早协议快照，包括旧裸输入或 if 端口引用。旧服务版本与任务终态仍可查看，不允许直接调用、回退激活或复制为可执行草稿。现有 NodeInput 资源可复用；请通过服务页重建流程并为原服务保存新实例；不会静默改写旧快照。

## 质量流程与模板版本

当前通用模板使用兼容 flow-6 的 `NodeInput` 资源，最小包与块版本为 3.0.0，完整包补充参考用途后为 4.0.0；文档出题业务的版本独立管理，出题包现为 6.0.0，不意味着所有通用模板都必须同号升级。不要只改版本号而不检查源码内容和快照冲突。

[文档质量实例](../examples/document-question-generation/README.md)放在 examples，samples 保持三类最小/完整模板。业务质量状态、审题枚举、修订次数不写入平台核心或摘要模板。业务模式可参考：模型只输出严格声明的决策，Python 条件块返回 bool；状态更新块用简单参考保留模型调用前主数据，显式增加轮次；循环零次退出后仍需最终验收。

接线前检查每个参考槽的数量、顺序和类型。零参考包放在普通节点之后时必须选择高级空列表；简单模式会提供一项前节点当次 primary。自定义 validator 的资源身份不能仅靠相似 JSON Schema 跨资源复用，应以显式 Python 转换/校验块建立边界；服务返回直接选择末块出口。

文档引用的行号属于业务契约：读取块在保留原始 text 的同时生成 numberedText，Prompt 从显式编号取行号，Python 按原文严格核验。通用文本模板不需要这个字段；业务契约改变后，应成套升级相关资源并通过服务页保存新实例，历史快照不会自动更新。

### 参考用途在卡片中的展示

参考数量与位置由 `NodeInput` 的固定元组声明；每个非零参考位置用 `Annotated[类型, Field(description="该位置参考的业务作用")]` 标注。完整包示范原文事实核对，完整契约的 `ReviewInput` 示范原始批次与结果对照；零参考模板保留 `tuple[()]`，卡片自动显示无需参考。类型自身的说明描述数据结构，不能代替位置用途。同一种类型在不同位置可以承担不同作用。修改已导入包或块的说明也会改变源码内容，应递增版本后重新加载；既有实例不自动升级。
