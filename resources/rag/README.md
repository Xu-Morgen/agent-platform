# 默认 PDF/DOCX 读取与最小 RAG 资源

核对日期：2026-09-24。

这些是可替换的普通资源，长期放在 `resources/rag/`，不占用 samples 的最小/完整模板位置。PDF 读取块声明固定文档解析依赖，通过平台 OCR 能力识别页面，其余块使用平台 SDK 与 Python 标准库；块本身不加载向量依赖、无持久化索引；可选语义块调用平台管理的 CPU 模型。共享数据契约由 SDK 的 `contracts/retrieval.py` 定义，独立入口为 `contracts.py`；平台编译器不引用该检索契约，也不识别专用 RAG 节点。

在服务页逐个加载 `blocks/*.py`、`answer/`，并加载 `contracts.py` 的 `RetrievalRequest` 和 `VerifiedAnswer`。无需聊天模型的读取/检索服务可以在 `EvidenceContext` 结束。

| 顺序 | 资源 | 输入 → 输出 | 参考输入 |
| --- | --- | --- | --- |
| 1 | `list_documents.py` | RetrievalRequest → DocumentSelection | 空 |
| 2 | `read_docx.py` | DocumentSelection → ParsedCorpus | 空 |
| 3 | `lexical_search.py` 或 `semantic_search.py` | ParsedCorpus → SearchResults | 空 |
| 4 | `select_evidence.py` | SearchResults → EvidenceContext | 空 |
| 5 | `answer/` | EvidenceContext → GroundedAnswer | 空 |
| 6 | `verify_answer.py` | GroundedAnswer → VerifiedAnswer | 上一步主数据，即 EvidenceContext |

除第一步外，第 2–5 步选择“高级参考：空列表”。第 6 步使用简单模式的上一节点主数据参考。聊天模型只绑定第 5 步；所有检索参数通过服务输入 `limits` 及 `terms` 设置，不存在块 Config。生成、核验属于可选下游，单纯文档预览不需要聊天模型，但新版读取块要求已选择平台 OCR 模型。

输入示例（知识库 ID 从页面选取）：

```json
{
  "knowledge": {"knowledgeId": "kb_实际标识", "revisionId": null},
  "query": "黑神话的文化与游戏设计",
  "terms": ["黑神话", "文化", "游戏"],
  "limits": {
    "maxDocuments": 20,
    "maxFileBytes": 10485760,
    "maxCharacters": 200000,
    "maxFragments": 300,
    "fragmentCharacters": 1200,
    "topK": 8,
    "contextCharacters": 12000
  }
}
```

`maxDocuments` 限制固定修订前 N 份文档；超过时 `scopeLimited` 为 true。读取按文档、XML 段落顺序进行，包括表格内段落；提取 `w:t`、将 tab/br/cr 转为空格、折叠连续空白，按 1 起算段落及规范化字符区间定位。DOCX 不读取页眉、脚注或图片，不伪造 DOCX 页码。PDF 按原始页面顺序提取，纯文字页读取文字层，扫描/混合页使用本地 OCR，按页码和字符区间定位规范化字符，OCR 页面额外带固定模型身份。读取 XML 上限 50 MiB；损坏或单文档超限是明确技术错误。总字符/片段上限会保留已扫描结果并标注受限。片段 ID 由文档版本、解析身份和定位共同产生。

词面检索优先采用 `terms`；为空时，中文连续文本拆为重叠二元组，英文/数字按词。最多 100 个去重检索词，不做同义词扩展。评分为命中词覆盖率×100加各词频次（每词最多 5 次），同分保留文档顺序。`topK` 和上下文上限选择完整片段，不再截断引文。词面匹配会遗漏同义改写、跨片段关系，也可能命中不相关的常用词；可用明确词缩小范围，或直接替换检索块。

登记记录包含实际扫描版本、范围限制、实际候选、选用证据和检索参数。平台补充调用节点及资源源码摘要；任务固定服务输入及资源快照，各执行步骤保存实际输出。引文核验只证明引文来自选用片段，不证明答案语义正确。空选用证据不是成功回答；默认包声明 `insufficient_source`。真实模型若返回平台通用的资料不足错误，任务仍会明确失败，不伪装成合格回答。

2026-09-21 离线验证：用户指定目录的 7 份 DOCX 正常读取，137 个片段、109 个词面候选、选用 8 条；无命中、扫描受限、段落定位与精确引文检查通过。该记录仅说明读取/检索及结构边界，不代表黑神话事实、出题质量或模型回答已验收。本次没有模型调用。

## 正文预览服务

加载 `prepare_preview.py` 和 `read_docx.py`，按“准备文档预览 → 读取 PDF/DOCX 正文”保存普通服务；输入选择前者主数据契约 `DocumentPreviewRequest`，输出选择后者 `ParsedCorpus`，两节点均选择高级参考空列表。保存后刷新知识库页面，下拉框只显示契约匹配且当前可执行的服务，单个候选自动选中；无候选时显示创建说明并禁用预览。知识库页面选择此服务，再点击文档的“预览正文”。页面提交 `{knowledge, versionId}`，实际解析与定位仍完全由上述普通资源负责。结果保存在普通任务历史中，包含 `reader` 身份、文档版本与段落定位；不在管理页实现另一套解析器。

## 替换检索方式

`alternatives/phrase_search.py` 是另一普通块，完整短语计数，不拆中文二元组；保持 `ParsedCorpus → SearchResults`。在已保存服务的草稿中移除词面检索节点、插入完整短语节点（仍置于读取和整理证据之间），高级参考保持空列表，保存新实例即可。读取、证据整理、下游模型包和平台核心无需修改。

2026-09-21：隔离桌面通过正式页面完成上述替换，服务生成 2.0 实例并成功执行；长查询作为完整短语未命中时返回空候选和空证据、`scopeLimited=false`，不冒充已回答。相同合成输入下，默认二元组能命中而完整短语无命中的差异已验证。黑神话业务出题、真实模型和人工质量验收仍需独立实验。

## 本地语义检索

先按 [模型说明](../../docs/local-embedding.md) 在平台设置导入并选择模型，将第 3 步替换为 `blocks/semantic_search.py`，高级参考为空，保存新服务实例。无需为该块选择聊天模型连接，也不计 LLM loop/token；默认选择在任务提交时固定。旧服务不会自动替换。

语义块忽略词面 `terms`，按完整 query 检索。超长片段调用平台 tokenizer 切分，保留原定位并追加零起算半开字符区间；切分超过 limits.maxFragments 时明确失败。默认 topK 无最低分，结果可能不相关，下游须检查资料不足。SDK 自定义块可以设置 minimumScore，空候选正常返回。

2026-09-22 的真实 CPU 模型、页面保存服务、来源追溯及词面对照见 [验收记录](../../docs/archive/2026-09-22/local-embedding-validation.md)：同义查询补充召回，无关问题暴露 topK 误召回边界。没有远端生成或审题调用，不代替默认回答包的质量验收。


## PDF/OCR 资源与升级

当前 `read_docx.py` 为 `rag-read-docx@3.0.0`，支持 PDF/DOCX 混合知识库；列举、预览准备、两种默认检索、短语检索替代及证据整理资源为 2.0.0，中间契约 DocumentVersion.format 接受 pdf/docx。算法未变的检索身份仍保留原算法版本。

在页面重新加载需要使用的上述块，再在服务草稿中替换对应节点，检查高级参考和节点引用，校验并保存新实例；预览服务还需重新选择新版 ParsedCorpus 输出契约。不能只替换读取节点而保留仅接受 DOCX 元数据的旧检索快照。业务包接收 EvidenceContext，其契约未变，无需改 Prompt。已保存实例不会自动升级。

读取块只声明 PyMuPDF 1.26.7、python-docx 1.2.0，通过 `ocr=True` 和异步 `context.ocr(...)` 使用平台 OCR。先在平台设置导入并选择就绪模型组合，再提交新版服务任务；即使只读取 DOCX 或纯文字 PDF，提交时也须固定该模型。引擎及模型准备统一见 [OCR 手册](../../docs/local-ocr.md)。旧版块内引擎和下载声明仅作为 [2.0.0 历史依赖记录](../../docs/archive/2026-09-22/knowledge-pdf-validation.md#读取块-200-历史依赖) 保留。

PDF 限制为 1～100 页；需要密码、结构损坏、OCR 无结果或置信度不足均明确失败。渲染限制为 6000 像素边长、2000 万像素，整次读取限 240 秒。总字符/片段上限仍显式标记 scopeLimited；空白页不生成证据，整份空白文档不会伪造正文。OCR 基本阅读顺序不保证复杂表格、多栏、倾斜或低清扫描件的质量，应预览核对。

旧服务和固定子服务不自动升级；含固定子服务时还须更新父流程引用。PDF 支持与平台 OCR 的逐轮验证分别见 [PDF 记录](../../docs/archive/2026-09-22/knowledge-pdf-validation.md) 和 [OCR 记录](../../docs/archive/2026-09-22/local-ocr-validation.md)，不覆盖新的远端回答或出题质量验收。
