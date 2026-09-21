# 文档导航

节点输入与 Python 条件块已完成并[归档](archive/2026-09-20/node-input-and-python-conditions-plan.md)，当前用法见 [samples/USAGE](../samples/USAGE.md)。文档出题质量目标已[完成归档](archive/2026-09-20/document-question-quality-plan.md)，当前使用见[实例手册](../examples/document-question-generation/README.md)与[验收记录](document-question-quality-validation.md)；总体路线见 [Agent 平台定位与分步计划](agent-platform-roadmap.md)，存储能力见 [桌面 PostgreSQL 持久化与验证](persistence.md)。

更新日期：2026-09-20。顶层只保留当前需求、架构、未完成计划和资源使用入口；已完成交付与过时设计集中保存在归档区。

## 当前文档

| 文档 | 何时查看 |
| --- | --- |
| [产品需求](product-requirements.md) | 确认当前范围、职责边界与产品行为 |
| [架构设计](architecture-design.md) | 修改流程、契约、快照、版本、预算或任务控制 |
| [文档出题质量与自主修订计划](archive/2026-09-20/document-question-quality-plan.md) | 已完成的规划、审题、有限修订实施及验收记录 |
| [产品细化计划](product-refinement.md) | 选择后续 R1–R4 工作，查看优先级与验收目标 |
| [三类资源专项计划](resource-plan.md) | 推进通用块、Prompt 业务包和独立契约的体验改进 |
| [资源指导手册](resource-guide.md) | 查找模板、配置说明、加载、接线和调用步骤 |
| [固定版本服务组合与契约选择](service-composition.md) | 将叶子服务加入拼图，选择固定版本、共享契约及查看嵌套记录 |
| [外部资源研发手册](external-development-guide.md) | 查询全部公开注入能力、函数签名、数据来源、API/context 用法及完整代码示例 |
| [平台运行文件与依赖](platform-runtime-files.md) | 依赖声明、独立环境、任务文件上传与运行上下文 |
| [文档出题质量验收记录](document-question-quality-validation.md) | 10 次 ds 真实调用、基线对照、真实修订、人工通过及正式页面保存 |
| [文档出题实例使用说明](../examples/document-question-generation/README.md) | 加载块、包与契约，配置线上模型，查看尚未完成的验收事项 |

启动和使用见 [项目入口](../readme.md)，开发约定见 [AGENTS.md](../AGENTS.md)。模型接入与桌面进程通信按需查看 [模型协议](protocols/model.md) 和 [控制协议](protocols/control.md)。

## 当前基线

- V1 拼图闭环已由用户于 2026-09-17 确认验证完成；当前唯一实例入口为服务页拼图。
- samples 每类只提供最小与最完整两套模板；通用块的 API 能力包含在 complete.py 中，原查重产品已移除。
- 2026-09-18 起业务包收敛为声明式 Prompt 包，平台统一调用模型，数据处理由通用块完成。
- 模型统一使用 OpenAI 兼容接口，token 按实际用量累计；API 环境保存 Base URL、凭据和超时，通用块节点选择连接并填写必填的 api.path，路径随实例版本保存。
- 桌面自动启动本地 PostgreSQL，数据跨重启保留；已完成 Ubuntu 24.04 上的数据库、加密与生命周期检查。优先事项见 Agent 平台分步计划。

## 归档与维护

[历史文档归档](archive/README.md) 保存 I1–I8 任务卡、交付证据、清理记录、旧迭代索引及精简前的需求与架构原文。历史阻塞状态、旧命令和旧协议只用于追溯，不作为当前开发入口。

新增文档优先补充现有主题；已完成记录或被替代的方案移入 `archive/日期/`，保留原文与归档说明，并同步修复引用。协议细节继续放在 `protocols/`，顶层导航仅链接仍需维护的内容。

2026-09-20 较早一轮的平台改造、文档读取与一次出题实施方案及本地验收记录已移入[历史归档](archive/README.md)，本轮节点输入与 Python 条件块也已完成并归档，文档出题质量资源已实现并完成授权真实调用，质量计划也已通过人工评审和正式页面验证并归档。此前开发验收脚本与回归测试均已清理；后续遵循 [AGENTS.md](../AGENTS.md) 中的测试和任务计划生命周期规则。
