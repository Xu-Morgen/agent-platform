# 退役资源与配置字段迁移对照

整理日期：2026-09-24。本页集中保存从当前手册移出的旧字段及入口迁移说明，供维护旧源码时参考；不是兼容执行协议或自动迁移入口。当前开发从 [资源手册](../../resource-guide.md) 进入，旧实例的只读与重建要求以 [协议升级](../../control-flow.md#协议升级) 为准。

## 旧业务包

原位置：`samples/packages/README.md`。

移除自定义 invoke、PackageContext、entry、runtimeRequirements、requiredCapabilities，以及 entry.py；把 Prompt 写入 prompt.txt。Config 改为继承 StrictModel，并移出预算字段。把前后处理和 API/块调用迁到独立通用块节点。节点将 capabilities.chat 改为 model，仅保留 environmentId/connectionId；单次输出限额改由节点 maxOutputTokens 配置。

旧完整包的 normalize/guidance 绑定已移除，数据规范化和外部信息查询改由独立通用块节点提供。

旧裸输入包须改为 NodeInput，并把 Prompt 改用 input.primary / input.references[0] 路径。旧清单和旧节点配置会被严格校验拒绝，不自动猜测迁移。修改后按当前资源版本规则递增版本、重新导入，通过页面重建并保存实例，不改写历史快照。

## 旧模型与预算配置

原位置：`samples/packages/CONFIGURATION.md`。

移除环境中的 `modelAdapter` 和预算中的 `strictTokenLimit` 字段；它们不再属于当前契约。模型连接只使用平台支持的 OpenAI 兼容协议，预算不提供严格 token 上界预留。现行字段见 [包配置参考](../../../samples/packages/CONFIGURATION.md)。

## 旧 API 节点与调用签名

原位置：`samples/USAGE.md`、`samples/blocks/README.md`。

旧节点配置需补充 `api.path`；旧块的 `api.request` 调用需移除路径参数。环境保存 Base URL、凭据和超时，节点保存路径，块定义方法、请求数据与响应契约。现行操作见 [API 块配置](../../../samples/blocks/README.md#完整块的-api-配置)。

## 旧模板与业务脚本

原 template、assignment-similarity、flow_templates.py 和 invoke_similarity.py 已移除，历史交接不作为当前模板入口。现用模板见 [samples](../../../samples/README.md)，不恢复原查重产品或旧流程导入脚本。

## 旧并发配置入口

`--run-concurrency` 和 `AGENT_PLATFORM_RUN_CONCURRENCY` 已退役；任务并发统一由平台设置持久化，重启后生效。当前操作见 [任务并发配置](../../../readme.md#任务并发配置)。

这些说明只保留迁移依据，不表示本轮执行了旧服务升级、模型调用或业务复验。
