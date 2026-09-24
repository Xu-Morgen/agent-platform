# 文档导航

更新日期：2026-09-24。当前文档保留产品说明、架构、操作手册与协议；当前无独立实施计划。已完成或退役的计划、阶段交付和验收记录放入 [历史归档](archive/README.md)。归档中的待办不自动成为当前任务，归档也不表示验收通过。

## 当前交付

平台已交付 flow-6 控制流、固定服务组合、PDF/DOCX 知识库、本地 embedding/OCR、任务并发和 PostgreSQL 持久化。知识库出题支持任意数量组合及公开结果整理；当前版本和质量边界集中在 [业务手册](../examples/black-myth-rag-question-generation/README.md)，不以早期固定三题人工验收覆盖新版。

## 关键说明

| 文档 | 内容 |
| --- | --- |
| [项目入口](../readme.md) | 启动、页面操作、任务并发设置与当前交付边界 |
| [产品说明与边界](product-requirements.md) | 平台职责、已实现能力、未实现事项及验收限制 |
| [架构说明](architecture-design.md) | flow-6、契约、快照、版本、任务调度、预算与取消 |
| [文档、知识库与最小 RAG](knowledge.md) | PDF/DOCX 管理、不可变版本、任务固定修订、证据历史及普通资源读取/检索 |
| [本地 OCR 管理与接口](local-ocr.md) | 模型组合导入/更换、任务固定、异步块能力、历史与资源升级 |
| [本地 embedding 操作](local-embedding.md) | 模型导入、选择、普通语义检索服务与 OCR 前置条件 |
| [本地 embedding 接口](local-embedding-contracts.md) | 模型清单、能力声明、任务搜索与管理 API |
| [知识库开发接口](knowledge-api.md) | TaskKnowledge、异步读取代理、证据登记与管理 API |
| [本地 PostgreSQL](persistence.md) | 安装与启动、数据目录、凭据、持久化和故障恢复 |
| [数组遍历与枚举分支](control-flow.md) | 服务流程图与 Mermaid/SVG 导出、foreach/switch 页面配置、作用域、教学源码与 flow-6 升级 |
| [资源指导手册](resource-guide.md) | 三类模板入口、加载、版本升级与归档 |
| [外部资源研发手册](external-development-guide.md) | NodeInput、函数签名、API/context、Prompt 与完整示例 |
| [运行文件与依赖](platform-runtime-files.md) | 文件上传、独立环境、依赖锁、模型缓存与块子进程 |
| [服务组合与契约选择](service-composition.md) | 一层固定版本服务嵌套、共享契约与参考用途展示 |
| [资源用途与 AI 解释](resource-explanation.md) | 说明字段、基于草稿的解释、数据发送范围与升级方式 |
| [模型协议](protocols/model.md) | 平台的 OpenAI 兼容请求、连接诊断与用量校验 |
| [桌面控制协议](protocols/control.md) | Electron 与后端的启动、就绪和退出通信 |

## 模板与业务示例

- [默认 RAG 资源](../resources/rag/README.md)：可替换的列举、PDF/DOCX 读取、词面/短语/本地语义检索、证据整理、回答包及引文核验；真实本地检索已验收，默认回答包没有新增远端验收。
- [samples](../samples/README.md) 与 [接线操作](../samples/USAGE.md)：通用块、Prompt 包、独立契约各提供最小和完整两套模板。
- [知识库出题](../examples/black-myth-rag-question-generation/README.md)：自然语言请求、三类题型、多文档证据、整体审题及有限修订；与旧全文出题实例独立。
- [文档出题实例](../examples/document-question-generation/README.md)：全文读取、规划、审题及有限修订；当前资源版本与真实模型待验收范围以该手册为准。

## 当前基线

平台使用 FastAPI、Pydantic、LangGraph、PostgreSQL 和 Electron。服务页 FlowDraft 是唯一实例配置入口；当前执行协议为 flow-6，模型只输出契约内的数据，Python 条件块控制分支和有限循环。旧协议历史只读，不执行或回退激活。按用户明确决定，不考虑多 Agent 与任务断点续跑，两者不列为后续待开发事项，详见 [产品说明](product-requirements.md)。

桌面自动管理本地数据库，资源、草稿、实例、设置与任务历史跨重启保留。单后端消费者池默认并发 4，支持 1～64；任务并发设置保存后重启生效，单任务内步骤按流程顺序执行。Python 通用块在独立子进程中执行，受信任代码不等于沙箱。

初版出题质量流程已有 10 次授权真实调用与人工评审记录；随后行号修复后的服务 2.0 及资源说明升级没有完成新一轮真实模型复验。AI 解释的真实远端效果、复杂文档 OCR、跨平台生命周期等限制见各手册，不能用历史或离线验收代替。

文档维护与任务清理遵循 [AGENTS.md](../AGENTS.md)。修改实现时同步相关说明；历史资料只作追溯，新增工作以用户明确需求为准。

## 文档维护职责

- `readme.md`：项目概览、启动和操作入口；不追加业务升级流水。
- `product-requirements.md`：产品范围、决策和未完成边界；`architecture-design.md`：执行机制与技术约束。
- 专项手册：当前操作、接口和限制。旧执行协议迁移统一见 [控制流手册](control-flow.md#协议升级)。
- `samples/README.md`：模板导航；`samples/USAGE.md`：加载与接线；分类文档：具体模板字段与用法。跨资源能力由 [研发手册](external-development-guide.md) 说明，专用接口以对应手册和源码为准。
- 业务手册：当前正式版本、资源升级及验收边界；`archive/`：分阶段历史证据。新增归档同步更新 [归档索引](archive/README.md)，不得把旧版通过结论套到新版。
- `AGENTS.md`：协作约束、必要授权和当前入口；不维护完整交付时间线。修改当前说明时更新核对日期和相关链接。
