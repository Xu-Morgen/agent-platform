# 知识库读取接口

核对日期：2026-09-24。本文维护知识库 SDK 与管理 API；操作与验收边界见 [知识库手册](knowledge.md)。

服务输入用 `agent_platform.contracts.knowledge.TaskKnowledge` 标记知识库引用；`revisionId: null` 表示提交时固定当前修订。任务保存 `knowledgeBindings` 和 `evidence`，旧记录缺省为空。

## 文档格式与原件

上传和替换版本接受 `.pdf` / `.docx`（扩展名不区分大小写），`DocumentVersion.format` 为 `pdf | docx`。同一逻辑文档允许跨格式替换，旧修订保留原格式、摘要和原件。下载 PDF 返回 `application/pdf`；受控 `knowledge_file` 副本使用对应 `.pdf` / `.docx` 后缀。

上传检查扩展名与签名、50 MiB 上限；DOCX 保留正文 XML 检查，PDF 完整结构、密码、页数及 OCR 错误由可替换读取块报告。上传成功不表示正文已解析或可用于出题。SDK 的 DocumentSelection / ParsedCorpus / SearchResults 包含 DocumentVersion，旧固定资源需通过页面重新加载和保存新实例。

## 任务内异步接口

通用块只通过现有 `context` 参数调用以下异步方法：

| 方法 | 请求契约 | 返回 |
| --- | --- | --- |
| `knowledge_resolve` | `KnowledgeReference` | `FixedKnowledgeReference`，只解析本任务绑定 |
| `knowledge_list` | `KnowledgePageRequest` | `KnowledgePage`，每页 1–200 条 |
| `knowledge_metadata` | `DocumentReadRequest` | `DocumentVersion` |
| `knowledge_file` | `DocumentReadRequest` | 当前调用专用原件副本的 `Path`；不得写入业务输出 |
| `knowledge_record` | `EvidenceRegistration` | `EvidenceRecord`，父进程补充实际节点及资源摘要 |

方法结构由同一 Pydantic 契约校验；摘要、候选/选用关系由登记边界显式校验，业务回答状态与引文由普通核验块检查，避免把不可静态证明的自定义关系校验引入跨资源接线；原件上限 50 MiB，可通过请求调低。候选最多 500 条、选用最多 100 条、单条正文最多 20000 字符、候选正文总量最多 1000000 字符。证据正文摘要、选用和候选一致性及修订成员归属均需校验。接口不对资源声明的解析算法作事实正确性背书。

使用版本 1 JSON 行协议，消息为 `type: knowledge` 消息，操作固定为 `resolve/list/metadata/file/record`。父进程负责范围、任务状态与取消检查，不传数据库、主密钥或原件存储路径。SDK 已按源码摘要锁定，因此新增方法不会静默进入旧资源快照；使用新接口需重新导入资源并保存实例。不增加资源类别或流程协议。

明确错误包括 `KNOWLEDGE_NOT_FOUND`、`KNOWLEDGE_ARCHIVED`、`KNOWLEDGE_SCOPE_ERROR`、`KNOWLEDGE_LIMIT_EXCEEDED`、`DOCUMENT_CORRUPTED`。归档限制新任务，历史固定引用继续保留。

单次登记参数 JSON 上限 64 KiB，单任务最多 100 次登记，超过上限明确报错。原件访问提供每次块调用专用的临时副本；副本修改不改变保存的原件，调用退出后清理。资源仍按受信任 Python 代码执行，此能力不是操作系统沙箱。任务预算与取消检查复用现有边界；读取不计模型 loop/token。

本地语义能力通过 `@block(..., semanticSearch=True)` 显式声明，提供 `context.semantic_split` 与 `context.semantic_search`；使用同一任务知识库范围与 Evidence 来源结构。模型选择、搜索契约和独立历史字段见 [embedding 接口](local-embedding-contracts.md)。不扩大 TaskKnowledge 范围，不隐式支持 TaskFile 或任意路径。

## 管理 API

管理 API 为 `/api/v1/knowledge` 的创建/列表、`/{knowledgeId}` 更新、`/{knowledgeId}/documents` 分页/单文件流式导入、`/documents/{documentId}` 逻辑移除、`/documents/{documentId}/versions` 历史版本和 `/versions/{versionId}/original` 获取原件。页面批量上传逐项调用同一导入 API 并显示成功/失败；版本替换通过 `documentId` 查询参数指定逻辑文档。保存知识库不生成服务实例版本，重新保存资源/检索配置仍遵守原实例版本规则。

正文预览候选使用 `GET /api/v1/knowledge/preview-services`，返回 `DocumentPreviewService[]`（`serviceId`、`instanceId`、`name`、`version`）。只包含当前协议可执行、输入接受 `{knowledge, versionId}` 且带知识库标记、输出兼容 `ParsedCorpus`、环境配置有效的当前服务。页面提交普通任务时携带候选的 `expectedInstanceId`，服务更新后需刷新重新选择。此接口不解析文档或修改旧服务。
