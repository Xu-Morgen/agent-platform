# 历史文档归档

本目录保存完成记录、过时方案和精简前原文。原有完成/阻塞状态与验证证据保持历史含义；归档仅调整链接并添加说明，不补造验收结果。当前开发从 [文档导航](../README.md) 进入。

## 2026-09-24 输出整理与文档维护

- [退役资源与配置字段对照](2026-09-24/legacy-resource-migration.md)：集中保存旧包入口、模型/预算字段、API 路径签名、模板脚本及并发配置迁移依据；当前开发使用现行手册。

- [知识库出题最终输出精简](2026-09-24/question-output-validation.md)：正式服务 8.0 页面升级、公开结果与无新增模型调用的验证。
- [手册历史验证摘录](2026-09-24/manual-validation-excerpts.md)：从当前说明退役的开发机状态、PostgreSQL、flow-5、AI 解释和通用块教学验证；不是本轮重新验收。

## 2026-09-22 知识库与出题升级

| 记录 | 范围及限制 |
| --- | --- |
| [正文预览修复](2026-09-22/document-preview-fix.md) | 预览候选契约筛选及页面调用 |
| [知识库 PDF 支持](2026-09-22/knowledge-pdf-validation.md) | PDF/DOCX 上传、替换、读取与证据，保留读取块 2.0.0 历史依赖；未做 PDF 出题真实模型验收 |
| [题量升级](2026-09-22/question-counts-validation.md) | 任意数量组合的执行验证；两道论述内容结论已被后续纠正 |
| [内容与溯源隔离](2026-09-22/question-content-validation.md) | 内部标识拒绝、原始需求核对和真实定向修订 |
| [语义检索出题](2026-09-22/question-semantic-validation.md) | 真实生成与资料不足；考点重叠误降 advisory 尚未修复，非全面内容质量通过 |
| [OCR 平台管理](2026-09-22/local-ocr-validation.md) | 模型组合管理、受控识别、读取块升级与实际验证边界 |

当前业务版本、使用方法和验收边界见 [知识库出题手册](../../examples/black-myth-rag-question-generation/README.md)。旧版通过不自动覆盖后续版本。

## 2026-09-22 本地 embedding

[实施计划与完成记录](2026-09-22/local-embedding-plan.md)、[真实模型与页面验收](2026-09-22/local-embedding-validation.md)：P1～P6 交付、模型来源与测量、语义/词面对照及取消/重启历史边界。当前入口为 [使用手册](../local-embedding.md)。

## 2026-09-21 计划与验收文档退役

按用户要求，docs 当前入口只保留关键说明。以下文件保留原始计划、当时状态和证据，仅修正迁移后的链接；未完成事项已汇总到 [产品说明](../product-requirements.md#7-未实现能力与验收边界)，不因退役标记为完成。

| 文档 | 历史用途 |
| --- | --- |
| [Agent 产品定位与实施步骤](2026-09-21/agent-platform-roadmap.md) | 持久化、节点输入、出题与后续扩展路线 |
| [产品细化计划](2026-09-21/product-refinement.md) | R1–R4 目标、页面交付与后续候选 |
| [三类资源专项计划](2026-09-21/resource-plan.md) | 块、包、契约的阶段改进及旧版样例基线 |
| [文档出题质量验收记录](2026-09-21/document-question-quality-validation.md) | 初版 10 次真实调用及人工通过证据、后续行号修复与未复验说明 |

## 2026-09-21 文档与知识库平台基础

[文档管理、知识库与最小 RAG 实施记录](2026-09-21/knowledge-rag-plan.md)：K1–K6 平台能力、普通可替换资源、Electron/PostgreSQL/子进程离线验证。当时按用户范围将黑神话出题及真实模型验收移交独立实验，本平台记录不认定业务验收通过。当前使用见[知识库手册](../knowledge.md)。

## 2026-09-21 控制流补完

[数组遍历与枚举分支](2026-09-21/control-flow-expansion-plan.md)：flow-6 协议、静态校验、foreach/switch 执行与编辑器、真实 Python 块及 Electron/PostgreSQL 生命周期验收。当前操作见[控制流手册](../control-flow.md)。

## 2026-09-21 桌面 UI 与任务并发

[整体 UI 优化记录](2026-09-21/ui-refresh.md)：统一四个工作区的视觉与响应式布局，包含验证结果与边界。

[单后端并发消费者池](2026-09-21/concurrent-consumers.md)：消费者生命周期及隔离验证。

[平台设置与任务并发持久化](2026-09-21/platform-settings.md)：页面保存落库、当前/待生效值与真实桌面重启验证。

## 2026-09-20 实施文档与验收整理

| 归档内容 | 保留原因 |
| --- | --- |
| [固定版本服务组合与选择器优化](2026-09-20/fixed-service-composition-plan.md) | 一层固定服务嵌套、共享契约身份、资源搜索分类与轻量验证记录 |
| [节点输入机制与 Python 条件块](2026-09-20/node-input-and-python-conditions-plan.md) | flow-5 实施、samples 2.0.0 适配、轻量验收与升级边界 |
| [平台文件与依赖改造计划](2026-09-20/platform-files-and-dependencies-plan.md) | 实现已交付，日常使用转入平台运行说明 |
| [文档出题质量计划](2026-09-20/document-question-quality-plan.md) | Q1–Q5、初版 10 次真实调用和人工确认；后续版本边界见业务手册 |
| [文档出题实施计划](2026-09-20/document-question-generation-plan.md) | 保留原始需求与实现记录，当前操作和待验收事项转入实例说明 |
| [文档读取与出题验收记录](2026-09-20/document-validation-record.md) | 保存当时的验证结果与边界；一次性脚本已删除，原文件可从 Git 提交 6fb84d3 查看 |

早期文档读取记录中的“未完成真实模型和人工验收”仅描述当时状态；后续初版质量流程已有 10 次真实调用与人工通过记录，行号修复后的服务 2.0 及后续资源升级仍未完成新版真实模型复验。当前资源、配置和待办见[实例说明](../../examples/document-question-generation/README.md)。

## 2026-09-18 文档整理

| 归档内容 | 保留原因 |
| --- | --- |
| [需求原文](2026-09-18/product-requirements.md) | 保留旧查重业务需求、首期验收与决策记录；当前范围已提炼到顶层需求 |
| [架构原文](2026-09-18/architecture-design.md) | 保留早期模型/接口示意、查重设计与迁移依据；有效规则保留在顶层架构 |
| [精简与架构评估](2026-09-18/cleanup-review.md) | 已完成的代码清理及当时的验证证据；仍适用的扩展边界保留在当前架构 |
| [旧迭代索引](2026-09-18/iteration-plan.md) | 保存 R0 清理、模板重建和 Prompt 包精简的交付记录；保留当时后续工作入口，相关计划也已退役 |

| 历史阶段 | 记录 |
| --- | --- |
| I1 工程与协议 | [任务卡](2026-09-18/tasks/i1.md) |
| I2 配置与版本 | [任务卡](2026-09-18/tasks/i2.md) |
| I3 执行与能力 | [任务卡](2026-09-18/tasks/i3.md) |
| I4 预算与终止 | [任务卡](2026-09-18/tasks/i4.md)、[平台交付](2026-09-18/delivery/i4-platform.md) |
| I5 原查重与模板 | [任务卡](2026-09-18/tasks/i5.md)、[查重交付](2026-09-18/delivery/i5-similarity.md) |
| I6 拼图契约 | [任务卡](2026-09-18/tasks/i6.md) |
| I7 拼图执行 | [任务卡](2026-09-18/tasks/i7.md) |
| I8 页面与业务迁移 | [任务卡](2026-09-18/tasks/i8.md)、[平台交付](2026-09-18/delivery/i8-platform.md)、[查重验收准备](2026-09-18/delivery/i8-similarity.md) |

I5/I8 中的真实模型验收阻塞保留为当时记录；2026-09-17 用户已确认 V1 验证完成，后续又移除了原查重产品。无需按历史任务恢复旧入口、测试脚本或验收数据。

## 2026-09-21 知识库三题业务

[实验实施计划](2026-09-21/black-myth-rag-experiment-plan.md)与[真实验收记录](2026-09-21/black-myth-rag-validation.md)：7 份授权 DOCX、27 个业务资源、正式页面 foreach/switch/while 服务、20 次真实调用及首轮失败修复。2026-09-22 人工验收通过；未触发的远端分支不宣称通过。当前使用见[业务手册](../../examples/black-myth-rag-question-generation/README.md)。
