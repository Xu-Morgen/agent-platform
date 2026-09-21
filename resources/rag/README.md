# 默认 DOCX 读取与最小 RAG 资源

这些是可替换的普通资源，长期放在 `resources/rag/`，不占用 samples 的最小/完整模板位置。仅依赖当前平台 SDK 与 Python 标准库，无向量依赖、无持久化索引。共享数据契约由 SDK 的 `contracts/retrieval.py` 定义，独立入口为 `contracts.py`；平台编译器不引用该检索契约，也不识别专用 RAG 节点。

在服务页逐个加载 `blocks/*.py`、`answer/`，并加载 `contracts.py` 的 `RetrievalRequest` 和 `VerifiedAnswer`。无需模型的读取/检索服务可以在 `EvidenceContext` 结束。

| 顺序 | 资源 | 输入 → 输出 | 参考输入 |
| --- | --- | --- | --- |
| 1 | `list_documents.py` | RetrievalRequest → DocumentSelection | 空 |
| 2 | `read_docx.py` | DocumentSelection → ParsedCorpus | 空 |
| 3 | `lexical_search.py` | ParsedCorpus → SearchResults | 空 |
| 4 | `select_evidence.py` | SearchResults → EvidenceContext | 空 |
| 5 | `answer/` | EvidenceContext → GroundedAnswer | 空 |
| 6 | `verify_answer.py` | GroundedAnswer → VerifiedAnswer | 上一步主数据，即 EvidenceContext |

除第一步外，第 2–5 步选择“高级参考：空列表”。第 6 步使用简单模式的上一节点主数据参考。模型只绑定第 5 步；所有检索参数通过服务输入 `limits` 及 `terms` 设置，不存在块 Config。生成、核验属于可选下游，单纯文档预览不需要模型。

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

`maxDocuments` 限制固定修订前 N 份文档；超过时 `scopeLimited` 为 true。读取按文档、XML 段落顺序进行，包括表格内段落；提取 `w:t`、将 tab/br/cr 转为空格、折叠连续空白，按 1 起算段落及规范化字符区间定位。不读取页眉、脚注、图片或 OCR，不伪造页码。读取 XML 上限 50 MiB；损坏或单文档超限是明确技术错误。总字符/片段上限会保留已扫描结果并标注受限。片段 ID 由文档版本、解析身份和定位共同产生。

词面检索优先采用 `terms`；为空时，中文连续文本拆为重叠二元组，英文/数字按词。最多 100 个去重检索词，不做同义词扩展。评分为命中词覆盖率×100加各词频次（每词最多 5 次），同分保留文档顺序。`topK` 和上下文上限选择完整片段，不再截断引文。词面匹配会遗漏同义改写、跨片段关系，也可能命中不相关的常用词；可用明确词缩小范围，或直接替换检索块。

登记记录包含实际扫描版本、范围限制、实际候选、选用证据和检索参数。平台补充调用节点及资源源码摘要；每个执行步骤也固定完整输入/输出及资源快照。引文核验只证明引文来自选用片段，不证明答案语义正确。空选用证据不是成功回答；默认包声明 `insufficient_source`。真实模型若返回平台通用的资料不足错误，任务仍会明确失败，不伪装成合格回答。

2026-09-21 离线验证：用户指定目录的 7 份 DOCX 正常读取，137 个片段、109 个词面候选、选用 8 条；无命中、扫描受限、段落定位与精确引文检查通过。该记录仅说明读取/检索及结构边界，不代表黑神话事实、出题质量或模型回答已验收。本次没有模型调用。
