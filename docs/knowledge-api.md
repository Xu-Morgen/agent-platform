# 知识库读取接口

K1 协议定稿（2026-09-21）。存储、页面和任务绑定由后续阶段接入。

服务输入用 `agent_platform.contracts.knowledge.TaskKnowledge` 标记知识库引用；`revisionId: null` 表示提交时固定当前修订。任务保存 `knowledgeBindings` 和 `evidence`，旧记录缺省为空。

通用块只通过现有 `context` 参数调用以下异步方法：

| 方法 | 请求契约 | 返回 |
| --- | --- | --- |
| `knowledge_resolve` | `KnowledgeReference` | `FixedKnowledgeReference`，只解析本任务绑定 |
| `knowledge_list` | `KnowledgePageRequest` | `KnowledgePage`，每页 1–200 条 |
| `knowledge_metadata` | `DocumentReadRequest` | `DocumentVersion` |
| `knowledge_file` | `DocumentReadRequest` | 当前调用专用原件副本的 `Path`；不得写入业务输出 |
| `knowledge_record` | `EvidenceRegistration` | `EvidenceRecord`，父进程补充实际节点及资源摘要 |

方法请求/响应由同一 Pydantic 契约校验；原件上限 50 MiB，可通过请求调低。候选最多 500 条、选用最多 100 条、单条正文最多 20000 字符、候选正文总量最多 1000000 字符。证据正文摘要、选用和候选一致性及修订成员归属均需校验。接口不对资源声明的解析算法作事实正确性背书。

沿用版本 1 JSON 行协议，新增 `type: knowledge` 消息，操作固定为 `resolve/list/metadata/file/record`。父进程负责范围、任务状态与取消检查，不传数据库、主密钥或原件存储路径。SDK 已按源码摘要锁定，因此新增方法不会静默进入旧资源快照；使用新接口需重新导入资源并保存实例。不增加资源类别或流程协议。

明确错误包括 `KNOWLEDGE_NOT_FOUND`、`KNOWLEDGE_ARCHIVED`、`KNOWLEDGE_SCOPE_ERROR`、`KNOWLEDGE_LIMIT_EXCEEDED`、`DOCUMENT_CORRUPTED`。归档限制新任务，历史固定引用继续保留。
