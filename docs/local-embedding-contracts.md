# 本地 embedding 契约与接口

已交付接口；用户操作见 [本地 embedding](local-embedding.md)，实施记录见 [归档计划](archive/2026-09-22/local-embedding-plan.md)。

权威模型为 `src/agent_platform/contracts/embedding.py`，由 Pydantic 推导 JSON Schema；不要手写另一份校验结构。搜索只对任务内的普通块开放，管理 API 不提供匿名全库搜索。

## 模型及任务快照

`EmbeddingManifest` 声明模型来源、版本修订、许可证、三个互异相对文件路径和 SHA-256、维度、token 上限、池化/归一化、文档/查询指令、精度及精确运行依赖。当前适配器是 `bert-onnx` v1，仅支持内嵌权重的 BERT 三个 int64 输入和 float32 token 输出；禁止外部张量文件、自定义算子、子图及模型 Python。实际支持环境及清单见 [制品目录](../resources/embedding/README.md)。

模型身份是完整规范化清单 JSON 的 SHA-256，带 `emb_` 前缀。文件摘要、tokenizer、指令或适配参数变更都会产生新身份。导入先复制、核对文件并真实编码，再原子发布；状态不是从清单自报取得。同一身份不覆盖历史文件。默认选择独立于需要重启的并发设置存储。

Run 的 `embeddingSnapshot` 固定完整清单及身份，`semanticSearches` 保存实际搜索记录。旧记录缺字段时分别为 null 和空列表，旧实例无语义能力时不要求选择模型。flow-6 不变，SDK 按既有源码摘要锁定，不自动改写历史资源、服务或运行依赖；新增接口需导入新资源并通过页面保存实例。

## 块声明与异步方法

```python
from agent_platform.blocks import block
from agent_platform.blocks.context import BlockContext
# 完整可加载源码：resources/rag/blocks/semantic_search.py
# @block(..., semanticSearch=True)
# async def run(value: NodeInput[ParsedCorpus, tuple[()]], *, context: BlockContext) -> SearchResults:
#     request = await context.semantic_split(request)
#     result = await context.semantic_search(request)
```

`semanticSearch=True` 必须是装饰器静态字面量，块必须为 async 并声明 context。快照识别包含条件、循环、所有分支及固定子服务；即使某次不走搜索分支，提交也固定模型。父进程拒绝未声明能力的调用，块不能替换任务固定模型。

| 方法 | 请求 | 返回 |
| --- | --- | --- |
| `context.semantic_split(request)` | SemanticSearchRequest | 同契约，fragments 改为 tokenizer 边界切分后的完整来源片段 |
| `context.semantic_search(request)` | SemanticSearchRequest | SemanticSearchResult |

请求包含 reference（FixedKnowledgeReference）、query、fragments（Evidence 列表）、splitter（解析切分身份）、scopeLimited、topK、可空 minimumScore。复用 Evidence 的文档 ID、版本、片段 ID、正文摘要、reader 及 locator。平台检查重复 ID、摘要、总量、任务引用、文档身份和版本归属；这不证明受信任解析器忠实还原原件。请求中的已有 score 不参与编码排名。

`semantic_split` 不读取或扩大知识库，按字符偏移返回原文无遗漏的片段；保留原定位并为新片段生成 ID。模型指令和特殊 token 计入上限，查询不会切分。调用者需进一步检查自身更小片段限额；默认资源已经实现。

`SemanticSearchResult` 包含 reference、完整 model、algorithm=`cosine-exact-v1`、splitter、scopeLimited、candidates、stats。topK 最大 100；阈值后无匹配、零输入片段都正常返回空候选。余弦分数有限且在 [-1,1]，同分稳定排序。响应不包含向量，父进程再次核对模型、范围和候选原文身份。

stats 包含 documentTokens、queryTokens、encodedFragments、cacheHits、batches、queueSeconds、inferenceSeconds；均为本地实际处理值，不是供应商账单。已缓存文档不重复累计编码 token；查询每次重新编码。模型加载耗时和峰值内存由诊断返回，不能把纯推理耗时当总任务耗时。

每个搜索由父进程追加 SemanticSearchRecord，包含节点、源码摘要、查询、topK、阈值和完整结果。向量只在任务模型进程内存；任务结束销毁。默认资源保持既有 `SearchResults` 与 `EvidenceContext`，模型身份串记录在 algorithm，详细统计保留在 Run 的独立搜索历史中；证据登记继续使用原有接口。

业务块使用版本 1 JSON 行代理的 `type: semantic`，操作为 `search/split_corpus`。本地模型进程另有受控内部通道。错误包括 EMBEDDING_NOT_SELECTED、EMBEDDING_NOT_READY、EMBEDDING_INCOMPATIBLE、EMBEDDING_INPUT_LIMIT、EMBEDDING_INFERENCE_ERROR、EMBEDDING_CAPACITY_EXCEEDED；范围、取消与退出沿用已有错误。上述错误不进入输出契约自动重试。

## 管理 API

所有路径以 `/api/v1/embedding` 为前缀，FastAPI 导出请求/响应 Schema。

| 方法与路径 | 契约 / 语义 |
| --- | --- |
| GET `/models` | EmbeddingModel[]，已导入模型与状态 |
| GET `/selection` | EmbeddingSelection |
| PUT `/selection` | EmbeddingSelection，modelId 可空；仅后续提交生效 |
| POST `/import` | EmbeddingImport `{directory}`，返回 202 EmbeddingJob |
| POST `/models/{modelId}/check` | 开始真实 CPU 小样例检查，返回 202 EmbeddingJob |
| GET `/jobs/{jobId}` | 进度、completed/failed、模型或诊断、错误原因 |

同时只接受一个导入/诊断操作，保留本会话最近 20 个操作状态。应用退出取消操作并清理临时目录。导入文件合计最多 512 MiB，启动恢复时再次核对持久副本。导入和选择不触发任务、不生成服务版本、不修改现有服务。
