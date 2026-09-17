# 业务包配置完整参考

配置分四处：**package.json 声明包是什么；Config 定义可调参数；节点配置决定本次实例怎么用包；环境保存外部连接。** 模板 JSON 使用对外 camelCase，Python 使用 snake_case。

## 1. package.json：所有清单字段

可直接复制 [最小清单](minimal/package.json) 或 [完整清单](complete/package.json)。顶层字段均必填，没有任意扩展字段。

| 字段 | 约束 | 作用 |
| --- | --- | --- |
| packageId | 英文字母开头，仅字母/数字/下划线/连字符 | 稳定的包身份，不是服务 ID |
| version | 三段数字版本，可带 `-alpha` 等后缀 | 同会话同 packageId/version 对应固定内容 |
| name | 非空字符串 | 页面名称 |
| description | 字符串，可为空 | 用途说明 |
| entry | `module:Symbol` | 实际执行函数，例如 entry:invoke |
| contractRefs.input | `module:Symbol` | 输入 StrictModel |
| contractRefs.output | `module:Symbol` | 输出 StrictModel |
| contractRefs.configuration | `module:Symbol` | 配置模型，必须继承 PackageBudget |
| runtimeRequirements.python | 非空 PEP 440 约束，例如 `>=3.12` | 检查后端 Python 版本 |
| runtimeRequirements.platformApi | 当前只能是 1 | 依赖的平台能力协议版本 |
| runtimeRequirements.dependencies | 必填列表，允许 [] | 检查已安装的 Python 分发包及版本，支持环境标记；不安装依赖，不支持 URL/extras |
| requiredCapabilities | 必填列表，允许 [] | 逐项声明依赖的 model/api/block 能力 |
| budgetDefaults | 必填对象 | 页面新建节点时使用的预算默认值；保存时仍须提交节点 budget |
| budgetDefaults.loopLimit | 正整数，字段默认 1 | 建议的节点包调用次数上限 |
| budgetDefaults.tokenLimit | 正整数，字段默认 32768 | 建议的节点累计 token 上限 |

`module:Symbol` 可以引用子模块，例如 `logic.entry:invoke`。只能引用包内可导入的模块和其导出符号；平台类型可先在 models.py 导入，再通过 models:ModelRequest 引用。包的输入、输出和能力模型必须是 StrictModel，不能直接用 str 作为包输入模型。

清单没有 Base URL、密钥、环境 ID、temperature、自动重试、hooks 或实例流程字段。若业务 Config 增加字段，只有入口代码实际读取并使用它才会改变行为；例如新增 temperature 不会自动扩展当前 ModelRequest 协议。

目录内容均参与摘要（忽略平台规定的缓存/依赖目录）。修改代码、Prompt 或 README 后，在同一会话重新加载须更新 version；相同版本不同摘要会 VERSION_CONFLICT。不要把用户配置、凭据或运行输出写回包目录。

## 2. requiredCapabilities：全部声明字段

| 字段 | 约束及作用 |
| --- | --- |
| capabilityId | 包内唯一标识，格式同 packageId；供 context 调用及节点 capabilities 键使用 |
| kind | model、api 或 block |
| inputModel | 输入模型符号引用 |
| outputModel | 输出模型符号引用 |

model 必须使用平台 ModelRequest/ModelResponse 契约。api/block 使用包定义的业务模型；块绑定时还会检查所选块的输入输出兼容性。API 响应的业务结构在真正请求返回后验证，不会在保存节点时探测远端。

所有声明都必须绑定，即使代码中的配置开关暂时不调用某能力。不存在 optional 或 defaultEnvironment 字段。无需某能力的独立版本应同时修改清单和入口。

## 3. Config 与节点配置

Config 继承的 loop_limit/token_limit 是平台预算。自定义字段例如 instruction、style 是业务参数，见 [完整包字段表](complete/README.md)。

每个包节点在 FlowDraft 的 `nodeConfigurations[nodeId]` 下单独配置，值结构如下：

| 字段 | 必填/默认 | 作用 |
| --- | --- | --- |
| parameters | 默认 {} | 仅放自定义业务参数；根据 Config 验证并补默认值 |
| budget | 必填对象 | 包节点累计预算 |
| budget.loopLimit | 默认 1，正整数 | 此节点在同一任务中可进入包多少次 |
| budget.tokenLimit | 默认 32768，正整数 | 此节点模型调用累计输入+输出 token 额度 |
| capabilities | 默认 {} | capabilityId → 实际绑定；须覆盖所有声明，不能多出未声明项 |

parameters 不允许 loopLimit/tokenLimit，也不允许对应 snake_case 名称。平台合并 parameters 与 budget 后校验 Config。同包两个节点可有不同参数、预算和连接。

完整节点示例：[minimal](minimal/node-configuration.example.json)、[complete](complete/node-configuration.example.json)。这些是**需要替换实际 ID 的配置示例**，不是自动发现的包文件。

## 4. capabilities 绑定字段

| 字段 | 默认值 | 作用及适用类型 |
| --- | --- | --- |
| kind | 必填 | 与能力声明一致 |
| environmentId | null | model/api 必填；当前会话保存环境得到的 ID |
| connectionId | null | model/api 必填；环境内连接 ID |
| artifactRef | null | block 必填；已加载块的 resourceId |
| apiMethod | null | api 必填：GET/POST/PUT/PATCH/DELETE |
| apiPath | 空字符串 | api 的相对路径；空字符串使用 Base URL 本身，否则以单个 `/` 开头，不带 query/fragment |

block 只填 kind/artifactRef，model 只填 kind/environmentId/connectionId，api 填 kind/environmentId/connectionId/apiMethod/apiPath。不要混用不同种类的字段。

API 地址为 `baseUrl.rstrip('/') + apiPath`。GET 将输入模型的字段放入 query，其他方法发送 JSON body。返回必须是成功状态码下的 JSON，模型会严格校验其结构；平台不会自动从 data 等包装中解包。需要转换时，应使用明确适配能力或修改接口契约。

## 5. 全局预算与请求输出上限

只要流程包含包，FlowDraft.budget 必填：

```json
{"loopLimit":1,"tokenLimit":32768,"strictTokenLimit":false}
```

| 层次 | loopLimit | tokenLimit | strictTokenLimit |
| --- | --- | --- | --- |
| package.json.budgetDefaults | 节点建议默认值 | 节点建议默认值 | 不支持 |
| nodeConfigurations[nodeId].budget | 单个节点在整次任务中的包调用次数 | 单个节点累计 token | 不支持 |
| FlowDraft.budget | 所有包节点的调用次数总和 | 所有节点累计 token | 默认 true；选择计量策略 |
| ModelRequest | 不支持 | 不支持 | 不支持；maxOutputTokens 只限单次输出 |

一次进入包计一轮 loop，包含后来失败的尝试；模型/API/块能力调用次数和 LangGraph 步数都不是包 loop。节点置于 repeat/while 内时累计。例如两个包节点各执行一次，局部 loopLimit 各 1，全局至少 2。

当前内置 ollama-chat/openai-chat 均不能保证严格 token 上限，含模型能力的服务必须显式选择 strictTokenLimit=false 才能通过配置预检。非严格模式仍检查累计额度；无可用用量且无法估算时会失败，超额也会失败，不代表关闭计量。默认 32768 不是对任意模型计量可用性的保证。

## 6. 环境连接：全部写入字段

环境在 `POST /api/v1/environments` 单独保存，请求顶层为 `name`（非空）和 `connections`（至少一个、connectionId 不重复）。返回 environmentId，随后用于节点绑定。

下面地址和模型名仅说明格式，必须替换为实际部署；不表示模板自带模型或 API 服务：

```json
{
  "name":"示例环境",
  "connections":[
    {
      "connectionId":"chat",
      "kind":"model",
      "baseUrl":"http://127.0.0.1:1234/v1",
      "modelAdapter":"openai-chat",
      "outputTokenParameter":"max_completion_tokens",
      "jsonMode":true,
      "model":"replace-with-real-model",
      "timeoutSeconds":60.0
    },
    {
      "connectionId":"guidance",
      "kind":"api",
      "baseUrl":"http://127.0.0.1:9000",
      "timeoutSeconds":30.0
    }
  ]
}
```

| 字段 | 必填/默认 | 作用 |
| --- | --- | --- |
| connectionId | 必填，标识格式 | 环境内部连接名称，供节点引用 |
| kind | 必填，model/api | 连接类型 |
| baseUrl | 必填 | HTTP(S) 基础地址，不包含用户名、密码、query、fragment |
| modelAdapter | 默认 ollama-chat | 模型协议：ollama-chat/openai-chat；API 连接不使用此字段 |
| outputTokenParameter | 默认 max_completion_tokens | OpenAI Chat 输出上限字段，可选 max_tokens；按真实服务支持情况选择 |
| jsonMode | 默认 true | OpenAI Chat 请求是否启用 JSON 对象模式；关闭也不免除响应 JSON 及业务校验 |
| model | 默认 null，model 连接必填非空 | 真实模型标识 |
| timeoutSeconds | 默认 60，有限正数 | HTTP 请求超时秒数 |
| credential | 默认 null，仅写请求 | 新凭据；非空，通过平台以 Bearer 认证使用，不写到包中 |
| credentialRef | 默认 null | 当前会话已有凭据引用；与 credential 二选一，也可均省略 |

OpenAI Chat 的 Base URL 若需 `/v1` 前缀须自行包含；适配器追加 `/chat/completions`。Ollama 使用根地址并追加 `/api/chat`。协议差异见 [模型协议](../../docs/protocols/model.md)。连接默认字段出现在 API 连接公开模型中不表示 API 获得模型能力。

环境、凭据和任务均为会话内存数据。占用中的环境不能修改；保存新配置不改动已提交任务固定的实例/环境。API 不提供在节点中任意定义请求头或直接嵌入密钥的配置。
