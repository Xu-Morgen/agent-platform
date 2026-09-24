# 文档导航

更新日期：2026-09-24。当前文档保留产品说明、架构、操作手册与协议；当前无独立实施计划。已完成或退役的计划、阶段交付和验收记录放入 [历史归档](archive/README.md)。归档中的待办不自动成为当前任务，归档也不表示验收通过。

当前能力与限制见 [产品说明](product-requirements.md)，操作按下表进入对应手册。

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
| [资源指导手册](resource-guide.md) | 模板入口、包目录快照范围、版本升级与归档 |
| [外部资源研发手册](external-development-guide.md) | NodeInput、函数签名、API/context、Prompt 与完整示例 |
| [运行文件与依赖](platform-runtime-files.md) | 文件上传、独立环境、依赖锁、模型缓存与块子进程 |
| [服务组合与契约选择](service-composition.md) | 一层固定版本服务嵌套、共享契约身份与选择规则 |
| [资源用途与 AI 解释](resource-explanation.md) | 契约与参考展示、基于草稿的解释、数据发送范围与升级方式 |
| [模型协议](protocols/model.md) | 平台的 OpenAI 兼容请求、连接诊断与用量校验 |
| [桌面控制协议](protocols/control.md) | Electron 与后端的启动、就绪和退出通信 |

## 模板与业务示例

- [默认 RAG 资源](../resources/rag/README.md)：可替换的列举、PDF/DOCX 读取、词面/短语/本地语义检索、证据整理、回答包及引文核验；使用前检查手册中的验收边界。
- [samples](../samples/README.md) 与 [接线操作](../samples/USAGE.md)：通用块、Prompt 包、独立契约各提供最小和完整两套模板。
- [知识库出题](../examples/black-myth-rag-question-generation/README.md)：自然语言请求、三类题型、多文档证据、整体审题及有限修订；与旧全文出题实例独立。
- [文档出题实例](../examples/document-question-generation/README.md)：全文读取、规划、审题及有限修订；当前资源版本与真实模型待验收范围以该手册为准。

文档维护与任务清理遵循 [AGENTS.md](../AGENTS.md)。业务版本与验收以业务手册为准，导航不维护调用次数、实例版本或重复的能力清单。

## 文档维护职责

- `readme.md`：项目概览、桌面与独立 API 启动命令和操作入口；安装命令与数据库准备由 `persistence.md` 维护，其他手册链接对应入口；不追加业务升级流水。
- `product-requirements.md`：产品范围、决策和未完成边界；`architecture-design.md`：执行机制与技术约束。
- 专项手册：当前操作、接口和限制。资源版本、包目录快照范围及归档规则由 `resource-guide.md` 维护；旧执行协议升级见 [控制流手册](control-flow.md#协议升级)，已退役字段仅在 [历史迁移对照](archive/2026-09-24/legacy-resource-migration.md) 保留。
- `samples/README.md`：模板导航；`samples/USAGE.md`：加载与接线；分类文档：具体模板字段与用法。跨资源能力由 [研发手册](external-development-guide.md) 说明，专用接口以对应手册和源码为准。
- 业务手册：当前正式版本、资源升级及验收边界；`archive/`：分阶段历史证据。新增归档同步更新 [归档索引](archive/README.md)，不得把旧版通过结论套到新版。
- `AGENTS.md`：协作约束、必要授权和当前入口；不维护完整交付时间线。修改当前说明时更新核对日期和相关链接。
- 同一规则只在负责文档中维护完整定义：架构维护快照与回退、环境占用、状态机、数据来源、作用域、重试和任务预算语义；USAGE 维护加载、模板接线、节点配置片段、草稿与正式流程的区别及保存与调用请求示例；产品说明保留对外调用的能力边界，架构说明维护 API 执行与错误语义，完整接口契约以运行中后端的 OpenAPI 为准；CONFIGURATION 维护包配置字段；CONTEXT 维护标准调用、占位符和包失败协议。
- 研发手册维护公开函数签名、参考用途标注及 API/context 调用方法；资源解释手册维护契约与参考展示；运行文件手册维护依赖与模型清单、准备流程、文件保留及子进程生命周期；模型协议维护连接字段及默认值、连接诊断、传输参数和响应校验；任务并发的默认值、范围及设置操作由 readme 维护，架构维护消费者调度机制。模板文档只解释具体示例，其他入口用短摘要和链接，阶段验收过程进入归档。
