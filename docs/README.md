# 文档导航

更新日期：2026-09-21。当前文档保留产品说明、架构、操作手册、协议及当前实施计划；已完成或退役的计划、阶段交付和验收记录放入 [历史归档](archive/README.md)。归档中的待办不自动成为当前任务，归档也不表示验收通过。

## 当前实施计划

数组遍历与枚举分支已完成并转入使用手册。以下知识库与业务实验仍仅完成规划，功能实施与业务验收尚未开始，按知识库基础与资源、业务实验的依赖顺序推进。

| 计划 | 内容 |
| --- | --- |
| [文档管理、知识库与最小 RAG](knowledge-rag-plan.md) | 平台基础管理与受控读取；通过现有契约、块、包提供可替换的最小检索实现 |
| [黑神话知识库出题实验](black-myth-rag-experiment-plan.md) | 基于 DOCX 生成单选、判断、论述各一题，验证控制流、检索、证据与业务质量 |

## 关键说明

| 文档 | 内容 |
| --- | --- |
| [项目入口](../readme.md) | 启动、页面操作、任务并发设置与当前交付边界 |
| [产品说明与边界](product-requirements.md) | 平台职责、已实现能力、未实现事项及验收限制 |
| [架构说明](architecture-design.md) | flow-6、契约、快照、版本、任务调度、预算与取消 |
| [本地 PostgreSQL](persistence.md) | 安装与启动、数据目录、凭据、持久化和故障恢复 |
| [数组遍历与枚举分支](control-flow.md) | foreach/switch 页面配置、作用域、教学源码与 flow-6 升级 |
| [资源指导手册](resource-guide.md) | 三类模板入口、加载、版本升级与归档 |
| [外部资源研发手册](external-development-guide.md) | NodeInput、函数签名、API/context、Prompt 与完整示例 |
| [运行文件与依赖](platform-runtime-files.md) | 文件上传、独立环境、依赖锁、模型缓存与块子进程 |
| [服务组合与契约选择](service-composition.md) | 一层固定版本服务嵌套、共享契约与参考用途展示 |
| [资源用途与 AI 解释](resource-explanation.md) | 说明字段、基于草稿的解释、数据发送范围与升级方式 |
| [模型协议](protocols/model.md) | 平台的 OpenAI 兼容请求、连接诊断与用量校验 |
| [桌面控制协议](protocols/control.md) | Electron 与后端的启动、就绪和退出通信 |

## 模板与业务示例

- [samples](../samples/README.md) 与 [接线操作](../samples/USAGE.md)：通用块、Prompt 包、独立契约各提供最小和完整两套模板。
- [文档出题实例](../examples/document-question-generation/README.md)：全文读取、规划、审题及有限修订；当前资源版本与真实模型待验收范围以该手册为准。

## 当前基线

平台使用 FastAPI、Pydantic、LangGraph、PostgreSQL 和 Electron。服务页 FlowDraft 是唯一实例配置入口；当前执行协议为 flow-6，模型只输出契约内的数据，Python 条件块控制分支和有限循环。旧协议历史只读，不执行或回退激活。按用户明确决定，不考虑多 Agent 与任务断点续跑，两者不列为后续待开发事项，详见 [产品说明](product-requirements.md)。

桌面自动管理本地数据库，资源、草稿、实例、设置与任务历史跨重启保留。单后端消费者池默认并发 4，支持 1～64；平台设置保存后重启生效，单任务内步骤按流程顺序执行。Python 通用块在独立子进程中执行，受信任代码不等于沙箱。

初版出题质量流程已有 10 次授权真实调用与人工评审记录；随后行号修复后的服务 2.0 及资源说明升级没有完成新一轮真实模型复验。AI 解释的真实远端效果、复杂文档 OCR、跨平台生命周期等限制见各手册，不能用历史或离线验收代替。

文档维护与任务清理遵循 [AGENTS.md](../AGENTS.md)。修改实现时同步相关说明；历史资料只作追溯，新增工作以用户明确需求为准。
