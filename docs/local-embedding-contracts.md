# 本地 embedding 契约与接入边界

P1 已实现契约及能力识别；推理、模型管理、SDK 方法和页面尚未交付。实施进度见 [当前计划](local-embedding-plan.md)。

权威模型为 `src/agent_platform/contracts/embedding.py`。公开 Schema 使用 Pydantic 的 `model_json_schema(by_alias=True)` 推导，不维护手写副本。

- `EmbeddingManifest`：受支持的 `bert-onnx` 适配器 v1、三个互异相对文件路径与 SHA-256、来源修订、许可证、维度、token 上限、CLS/mean 池化、归一化、文档/查询指令、float32、精确运行依赖和 Python 范围。目前声明 Linux x86-64，其他平台未验证。导入不执行 Python、不按清单自动安装依赖；P2 必须核对实际支持组合。
- 身份是完整规范化清单 JSON 的 SHA-256，带 `emb_` 前缀。文件摘要、tokenizer、指令、依赖或适配参数变化都产生新身份。导入器在 P3 验证实际文件摘要后复制并原子发布。结构合法不等于就绪。
- `EmbeddingSnapshot` 固定完整清单及身份，运行记录新增可空 `embeddingSnapshot`。旧记录缺字段时读作 null；默认选择将在独立模型设置存储中持久化，不混入需要重启的任务并发设置。提交阶段固定选择；变更不生成服务版本。
- 块使用 `@block(..., semanticSearch=True)`，必须是 async 并声明 `context: BlockContext`。静态 AST 与实际装饰器使用同一 `BlockMetadata`；快照遍历包含条件、循环、分支及固定子服务。尚未配置运行时时提交明确报 `EMBEDDING_NOT_READY`，不执行半成品。
- `SemanticSearchRequest` 复用 Evidence 的文档、版本、定位、正文和摘要，限定一个固定知识库修订、最多 500 片段/一百万字符、topK 1～100，允许零片段。校验空白查询、重复 ID、正文摘要和引用一致性；父进程另核对任务绑定和文档版本归属，不能只相信块输入。
- `SemanticSearchResult` 返回候选、完整模型身份、切分标识、范围限制及独立本地统计。余弦分数有限且在 [-1,1]，降序且 ID 唯一；同分保持输入顺序。topK 与输入来源一致性由运行时再次检查。不公开向量。

## 协议与历史

保持 flow-6：这是块能力的显式增量，没有改变现有输入封装、控制流或编译规则。旧块缺省 `usesSemanticSearch=false`，现有源码摘要保持原值，不自动替换固定资源。运行身份仍按现有 SDK 内容摘要锁定；历史恢复须验证已固定依赖，不重写历史摘要。包含新能力的资源由源码声明进入新快照；P4 接通 SDK/代理后才可执行。

不在现有 `SearchResults` / `EvidenceContext` 中增加字段，以免改变已有业务资源严格契约。默认新块保持 `ParsedCorpus → SearchResults`，模型、检索参数和处理统计由父进程单独记录（P4），证据登记沿用 `EvidenceRegistration.parameters`。默认块的 tokenizer 切分能力随 P2/P4 实现，须保留字符偏移定位，禁止静默截断。

## 接线和生命周期（后续实施约束）

- P3：模型仓储复用平台 store 文档持久化，文件置于应用专用目录；导入/列举/选择/诊断管理接口接入现有设置页。模型选择独立写入，旧并发表单不会清空它。
- P4：`RunSubmission` 原子固定模型到 Run；`FlowRunContext` 管理任务工作进程与缓存，业务块子进程用父进程代理访问。语义代理要求能力声明和任务固定身份，拒绝任务任意选模型。
- 缓存键含任务、完整模型身份、文档版本、解析/切分标识、正文摘要及编码用途；父进程容量控制后再启动任务模型进程。仅完整成功批次可缓存，取消/失败/退出均终止进程并释放容量。并发、线程、批次默认值待 P2 实测。
- 本地 token、批次、缓存命中、排队/推理耗时单独记录，不累计 LLM loop 或收费 token；不将向量写入 Run、节点输出或日志。重启沿用 `APPLICATION_INTERRUPTED`。
- 新错误：`EMBEDDING_NOT_SELECTED`、`EMBEDDING_NOT_READY`、`EMBEDDING_INCOMPATIBLE`、`EMBEDDING_INPUT_LIMIT`、`EMBEDDING_INFERENCE_ERROR`、`EMBEDDING_CAPACITY_EXCEEDED`；沿用知识库范围错误与取消/退出错误。这些错误不属于现有输出契约重试集合。
