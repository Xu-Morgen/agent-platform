# 加载、接线和调用模板

核对日期：2026-09-24。

先按 [项目启动说明](../readme.md#启动) 启动桌面或独立 API；首次使用需完成其中链接的环境准备。以下请求发送到实际后端地址，接口文档位于该地址的 `/docs`。

桌面和独立 CLI 默认使用同一持久化数据目录，不能同时占用该目录；隔离开发和临时存储选项见 [持久化说明](../docs/persistence.md#新环境准备)。

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

加载 `samples/blocks/complete.py`，服务端口选其 primaryContract/outputContract，添加 normalize 节点并保持首步零参考。按 [完整块的 API 配置](blocks/README.md#完整块的-api-配置) 绑定真实 API 连接和路径，提交 `{"query":"greeting"}`；输入选项、响应要求和预期输出见该模板说明。只有通用块时无需模型连接或任务预算。

### 模板之间的接线

| 组合 | 页面配置与转换要求 |
| --- | --- |
| 最小块 → 最小包 | 主数据结构兼容；最小包声明零参考，须切换高级模式并设为空列表 |
| 完整块 → 最小包 | 加入转换块，仅输出完整的 `{text: ...}`；完整块的统计字段不能直接传给包，包参考设为空列表 |
| 最小块或完整块 → 完整包 | 加入转换块，在出口契约中声明并实际验证 text 为 1～10000 字符；现有块的出口没有此保证，即使某次文本符合也不能跳过静态检查 |
| 完整包的唯一参考 | 独立运行时绑定服务输入；接在转换块后时，默认参考是转换块当次 primary，只有该来源也满足包的 Input 约束才可保留，否则显式绑定兼容来源 |
| 完整独立契约 | 演示批次结构，需配套处理节点，不能直接替换文本示例端口 |

平台不执行字段映射、改名或隐式类型转换。转换块必须输出目标所需的完整对象，参考按槽位顺序另行校验。

## 4. FlowDraft 的公共配置

| 字段 | 必填/默认 | 作用 |
| --- | --- | --- |
| draftId | 可省略 | 可选草稿标记，不是可调用的 serviceId |
| name | 必填，非空 | 流程名称 |
| inputContract / outputContract | 必填 | 已加载的服务端口契约引用 |
| flow | 必填列表 | 顺序执行的节点及控制容器 |
| retryLimit | 默认 3，整数 0～1000 | 可归因的生产节点契约错误的最大额外重试次数；0 表示不重试，静态类型不兼容直接拒绝保存；适用范围见 [校验与重试规则](../docs/architecture-design.md#58-节点输入校验与重试) |
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

### 固定服务节点

| 字段 | 作用 |
| --- | --- |
| nodeId | 整个流程内唯一，使用与块/包节点相同的标识规则 |
| kind | 固定为 service |
| serviceId | 已保存服务的稳定标识 |
| instanceId | 该服务中明确选择的固定实例标识 |

服务节点不声明 artifactRef、references 或独立 nodeConfigurations；内部配置来自固定子实例。页面添加、叶子实例限制及预算累计见 [服务组合手册](../docs/service-composition.md)。

### 分支与循环的数据来源

以下为来源对象内部的字段；外层是否需要数组或 source 包装，由使用位置决定。

| 来源字段 | 作用 |
| --- | --- |
| kind=input | 引用服务输入，不填 nodeId |
| kind=node | 引用可见前序节点输出，必须填 nodeId |
| kind=carry | 引用循环当前携带值，nodeId 填循环节点 ID |
| kind=item | 引用可见 foreach 的当前完整元素，nodeId 填 foreach 节点 ID |
| kind=constant | 直接填符合接收方契约的完整 value；仅用于分支 output 和循环 carry.initial/update，不填 nodeId/path |

| 使用位置 | 字段值示例 | 结构约束 |
| --- | --- | --- |
| if 的 thenBranch.output / elseBranch.output、switch 的 cases[].output | `[{"source":{"kind":"input"}}]` | 恰好一项的绑定数组，每项含 source；允许 constant |
| repeat/while 的 carry.initial | `[{"source":{"kind":"constant","value":{"text":"初始值"}}}]` | 恰好一项的绑定数组；完整值必须符合 carry.contract |
| repeat/while 的 carry.update | `[{"source":{"kind":"node","nodeId":"step"}}]` | 恰好一项的绑定数组；示例 step 须在本轮循环体中已执行，输出符合 carry.contract |
| foreach.source | `{"kind":"input"}` | 单个引用对象，不套数组或第二层 source，不支持 constant；数组位置由 arrayPath 指定 |
| 块/包的 references | `[{"kind":"input"}]` | 按槽位排列的引用数组，每项直接是引用对象，不套 source，不支持 constant |

表中示例是对应字段的值，不是完整节点或 FlowDraft。分支 output 和 carry.initial/update 均不能使用空数组或多项绑定来隐式合并字段。字段结构由 [流程契约](../src/agent_platform/contracts/flows.py) 定义，绑定数量及作用域在流程预检时检查。

普通节点主数据自动接入，无需配置上述 source。展开节点的高级参考设置，按资源声明的槽位选择完整来源；零参考资源放在后续位置时明确设置 `[]`。服务返回选择输出契约，字段选取或结构转换使用通用块。

各位置的默认参考、作用域及数据隔离规则见 [架构说明](../docs/architecture-design.md#55-流程结构端口与数据作用域)；类型声明见 [研发手册](../docs/external-development-guide.md#31-类型声明)。保存或执行失败时，按 [校验与重试规则](../docs/architecture-design.md#58-节点输入校验与重试) 判断错误归属。

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
| 保存草稿 | POST /api/v1/drafts，`{content: 编辑内容对象}`；按 DraftWrite 保存，可缺少流程字段 |
| 预检 | POST /api/v1/flows/validate，同一 DraftWrite 请求；尝试按 FlowDraft 校验，返回 valid/issues |
| 创建稳定服务 | POST /api/v1/services，`{name, flow: FlowDraft}` |
| 保存新实例版本 | POST /api/v1/services/{serviceId}/versions，同上 |
| 获取业务契约 | GET /api/v1/services/{serviceId}/schema |
| 提交任务 | POST /api/v1/runs，`{serviceId, input}`；可带 expectedInstanceId |
| 查询状态/结果 | GET /api/v1/runs/{runId}；GET /api/v1/runs/{runId}/result |
| 取消任务 | POST /api/v1/runs/{runId}/cancel |

`DraftWrite.content` 是 JSON 对象，保存草稿不要求通过 FlowDraft 校验；例如 `{"content":{"name":"未完成流程"}}` 可以保存。正式创建服务或保存版本的 `flow` 才必须满足完整 FlowDraft 及接线、配置预检。更新已有草稿使用 `PUT /api/v1/drafts/{draftId}`，请求体仍为 DraftWrite。

任务执行记录与包用量显示“业务包或通用块名称（node_x）”，分支和循环内的条件块也显示名称；历史任务按自身实例解析名称，不使用当前服务版本替换。

草稿不可直接调用；每次成功保存实例都会生成新版本并立即切换稳定服务入口，即使内容未变。版本分类见 [编号规则](../docs/architecture-design.md#4-核心模型与标识)。已提交任务固定代码、配置及实际环境。存储模式、退出与恢复语义见 [持久化说明](../docs/persistence.md)。

资源版本、同版本内容冲突、只展示最新已导入版本及归档/恢复规则统一见 [资源手册](../docs/resource-guide.md#更新与归档资源)。升级服务须替换草稿节点并保存新实例；恢复旧资源的归档状态不会让它重新成为新增候选。

## 文件输入与运行环境

任务页根据 `TaskFile` 契约显示 PDF/DOCX 上传控件，保存成功后再提交。完整块模板可带附件，但不解析正文；依赖及模型清单为空。文件限制、保留策略、资源准备阶段和取消方式见 [运行文件与依赖](../docs/platform-runtime-files.md)。

## 文档业务组合

[文档出题实例](../examples/document-question-generation/README.md) 演示文件上传、全文读取、规划、审题及有限修订。当前资源、接线及真实验收边界以该业务手册为准。

## 升级旧协议

flow-5 及更早实例仅供历史查看，不能执行、回退激活或直接复制为新协议草稿。通过页面重建 flow-6 实例；完整步骤及固定子服务顺序见 [协议升级](../docs/control-flow.md#协议升级)。

## 参考用途在卡片中的展示

接线前按卡片显示的参考数量、位置和用途选择完整来源。展示规则见 [资源用途说明](../docs/resource-explanation.md#契约与参考展示)，开发者标注方式见 [参考用途声明](../docs/external-development-guide.md#33-声明参考位置的用途)。
