# Prompt 包配置参考

核对日期：2026-09-24。

包负责契约和 Prompt；节点负责业务参数取值、模型连接和执行预算；任务另设全局预算。对外 JSON 使用 camelCase。

## package.json

| 字段 | 必填/默认 | 用途 |
| --- | --- | --- |
| packageId | 必填 | 英文字母开头，仅字母、数字、下划线、连字符 |
| version | 必填 | 三段版本，例如 1.0.0；同版本必须对应相同内容 |
| name | 必填 | 非空显示名称 |
| description | 默认空字符串 | 用途说明 |
| contractRefs.input | 必填 | NodeInput 入口引用，例如 models:Entry；业务主数据从其 primary 推导 |
| contractRefs.output | 必填 | 输出模型引用，例如 models:Output |
| contractRefs.configuration | 可省略/null | 业务参数模型，例如 models:Config；省略时只接受空 parameters |
| prompt | 默认 prompt.txt | UTF-8 Prompt 文件的包内规范相对路径 |
| budgetDefaults | 可省略/null | 新节点的默认最大调用次数和累计 token；未指定时使用平台默认值 |
| budgetDefaults.loopLimit | 默认 4 | 节点在单任务中累计进入包的次数上限 |
| budgetDefaults.tokenLimit | 默认 32768 | 节点在单任务中累计输入与输出 token 上限 |

输入、输出和 Config 都继承 StrictModel。Config 不继承预算类型。只有实际引用的业务参数影响 Prompt，不存在隐式执行逻辑。依赖平台提供的契约工具，无需维护代码依赖、执行入口或模型协议声明。清单只接受当前声明的字段。

## 节点配置

FlowDraft.nodeConfigurations[nodeId]：

```json
{
  "parameters": {},
  "model": {"environmentId": "replace_environment_id", "connectionId": "chat"},
  "budget": {"loopLimit": 4, "tokenLimit": 32768},
  "maxOutputTokens": 512
}
```

| 字段 | 必填/默认 | 用途 |
| --- | --- | --- |
| parameters | 默认 {} | 仅业务参数；根据可选 Config 验证并补默认值 |
| model | 必填 | environmentId、connectionId 指向已保存的 model 连接 |
| budget | 可省略/null | 省略时取包 budgetDefaults，再取平台默认值；保存后成为固定节点配置 |
| budget.loopLimit | 默认 4，正整数 | 单任务内此节点最大调用次数 |
| budget.tokenLimit | 默认 32768，正整数 | 单任务内此节点最大累计 token |
| maxOutputTokens | 默认 512，正整数 | 单次请求输出上限，平台可能按剩余额度收紧 |

预算不与 parameters 合并，也不注入包契约。节点显式 budget 优先于包默认值；显式对象内省略的字段使用节点类型默认值。包配置是初始化建议，最终强制限额来自保存后的节点和任务。相同包的不同节点互不影响；同一节点在循环内累计计量。

### 最小包节点配置示例

以下配置用于平台节点，不是业务包文件。替换实际环境 ID 后，在节点配置中使用；省略 budget 时最小包采用平台默认限额 loopLimit=4/tokenLimit=32768，此处将单次输出上限设为 256。

```json
{
  "parameters": {},
  "model": {
    "environmentId": "replace_environment_id",
    "connectionId": "chat"
  },
  "maxOutputTokens": 256
}
```

## 任务预算

含包的 FlowDraft.budget 必填：

```json
{"loopLimit": 4, "tokenLimit": 32768}
```

全局 loopLimit 限制所有包节点的累计调用次数，tokenLimit 限制累计模型输入与输出 token，两者均为正整数。任务与节点上限同时生效，失败与重试均计调用；预算不足可能提前终止重试。token 按供应商实际用量累计，单次请求仍可能超额，缺少 usage 时失败。计数时机、输出收紧及终态边界见 [架构预算规则](../../docs/architecture-design.md#9-loop-与-token-预算)。

## 模型环境

在环境页或 POST /api/v1/environments 保存连接，之后在节点 model 中引用：

```json
{
  "name": "示例模型环境",
  "connections": [{
    "connectionId": "chat",
    "kind": "model",
    "baseUrl": "http://127.0.0.1:1234/v1",
    "outputTokenParameter": "max_completion_tokens",
    "jsonMode": true,
    "model": "replace-with-real-model",
    "timeoutSeconds": 60.0
  }]
}
```

地址和模型名需替换为实际部署。连接支持 credential（写入新凭据）或 credentialRef（引用平台已保存凭据），二选一；两者也可省略。凭据不进入包或 Prompt。Base URL 不能包含认证信息、query 或 fragment。

模型统一使用 OpenAI 兼容 Chat Completions，无协议选择字段。outputTokenParameter 默认 max_completion_tokens，也支持 max_tokens；jsonMode 默认 true；timeoutSeconds 默认 60。平台在 Base URL 后追加 /chat/completions。关闭 JSON 模式也不免除输出 JSON 与业务结构校验，详见 [模型协议](../../docs/protocols/model.md)。

默认 PostgreSQL 模式持久化环境、凭据及任务记录，重启后恢复；只有显式 `--memory` 模式使用会话内存。已提交任务固定实际环境。存储与凭据恢复见 [持久化说明](../../docs/persistence.md)。业务包只能选择 kind=model 的连接；外部 API 的连接引用与请求路径由 [API 通用块节点](../blocks/README.md#完整块的-api-配置) 单独配置，查询结果通过接线传入包。

历史字段迁移见 [退役配置对照](../../docs/archive/2026-09-24/legacy-resource-migration.md)。
