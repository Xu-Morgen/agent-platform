# 三类资源指导手册

当前模板已按资源类型重建，完整开发说明与示例代码放在 samples 内，避免操作手册和模板各维护一套定义。

| 需要了解的内容 | 当前入口 |
| --- | --- |
| 三类资源的区别、最小交付物和目录 | [samples/README.md](../samples/README.md) |
| 通用块：创建、入口出口、元数据、输入选项、同步/异步函数 | [blocks/README.md](../samples/blocks/README.md) |
| 业务包：目录、创建步骤、清单和 Prompt | [packages/README.md](../samples/packages/README.md) |
| 业务包全部配置：清单、节点、模型、预算、环境 | [CONFIGURATION.md](../samples/packages/CONFIGURATION.md) |
| 平台标准入口、Prompt 占位符、输入输出校验和错误 | [CONTEXT.md](../samples/packages/CONTEXT.md) |
| 独立契约：symbol、类型、字段约束、校验器与兼容性 | [contracts/README.md](../samples/contracts/README.md) |
| 资源加载、服务接线、控制结构、保存与调用 | [USAGE.md](../samples/USAGE.md) |

推荐从无需模型的最小块闭环开始，再配置最小业务包。每类完整示例都明确每项配置的作用、默认值和入口出口，不要求先理解其他业务产品。

配置与源码以当前平台实现为准：块选项通过输入接线，包参数通过节点配置，独立契约只描述端口。平台统一执行业务包，不提供自定义入口或生命周期 hooks。包只声明契约、参数和 Prompt；处理和转换通过通用块节点完成。

原 template、assignment-similarity、flow_templates.py 和 invoke_similarity.py 已按用户要求移除，历史交接不作为现用模板指南。后续产品体验改进见 [三类资源专项计划](resource-plan.md)。
