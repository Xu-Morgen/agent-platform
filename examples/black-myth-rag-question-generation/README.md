# 知识库出题

独立于旧全文出题实例的业务资源，仅支持单选、判断、论述，允许任意数量组合（总数至少一道）。根据任务固定的知识库修订检索并出题，题干限定“根据材料”；材料观点不被当作已核实的现实事实。当前用法、正式版本及验收边界统一维护在本页；各轮历史证据见文末。

## 当前正式服务

核对日期：2026-09-24。正式“知识库出题 · ds”为 **8.0**，服务 `svc_303e8991d0124b4eb92de3fbc0b4edc3`，实例 `ins_df856a4c603a4c82be1ec66e8b2860a7`。使用本地 BGE 语义检索，在原内部流程末尾增加 `rag-question-present-result@1.0.0`，只返回公开题目结果。

8.0 保留此前业务资源 4.0.0、DOCX 检索资源及预算，仅升级最终返回。仓库提供的 PDF/OCR 新版资源尚未自动进入该正式实例；从当前源码新建服务须按下文准备 OCR。此次输出整理未调用模型，未修复考点重叠被审题降为 advisory 的内容质量问题。

## 资源与契约

`contracts.py` 是内部流程契约源，使用 `sync_contracts.py` 同步到 8 个 Prompt 包和 20 个独立块；对外交付契约 `PublicResult` 由 `blocks/present_result.py` 定义；`--check` 检查副本一致性。同步工具不导入资源、不绑定环境、不创建服务。修改契约后须同步资源并升级版本，再从页面重新导入；既有实例不自动改变。

新建服务前在平台设置选择就绪的 embedding 模型及 OCR 模型组合；当前知识库读取块 `rag-read-docx@3.0.0` 即使只读 DOCX 也要求提交时固定 OCR 模型。操作见 [embedding](../../docs/local-embedding.md) 与 [OCR](../../docs/local-ocr.md)。

页面加载本目录 8 个包目录、`blocks/*.py`，以及默认 `resources/rag/blocks/` 中的 `list_documents.py`、`read_docx.py`、`semantic_search.py`、`select_evidence.py`。从独立 `contracts.py` 加载 `Request`、`Result`、`QuestionEnvelope`、`State`；可从资源端口选择其他契约。

## 页面拼图

所有流程在正式服务页配置；下面是操作说明，不是手写实例导入协议。普通节点默认选择高级参考空列表，只有表中列出的节点添加参考。输出来源均选对应分支最后节点。

1. 服务输入 `Request`，输出选择 `present_result` 块的 `PublicResult` 出口契约。解析请求包 → 规范化块（参考服务输入）。
2. 请求 switch，路由 `route_request`，统一出口 `Result`。unsupported 分支为 `unsupported` 块。supported 分支继续下列步骤。
3. `prepare_retrieval` → 默认列举/读取/本地语义检索/整理证据四块 → 规划包（参考规范化输出）→ `merge_plan`（依次参考整理证据输出、规范化输出）。
4. 资料 switch，路由 `route_plan`，统一出口 `Result`。insufficient_source 分支为 `insufficient` 块。sufficient 分支继续。
5. foreach 从规范化节点输出选择 `items`，按实际运行范围设置最大条数，不能保留旧版 3 项限制，每项出口 `QuestionEnvelope`。体内 `prepare_question`（参考 `merge_plan` 输出）→ 题型 switch（路由 `route_question`，统一出口 `QuestionEnvelope`）。single_choice/true_false/essay 各为对应生成包 → 对应 `wrap_*` 块。switch 后 `verify_question`，参考当前迭代 `prepare_question` 输出。
6. foreach 后 `collect`（参考 `merge_plan` 输出）→ 整体审题包 → `merge_review`（参考 `collect` 输出）。
7. while，条件 `needs_revision`，最多 2 轮，携带 `State`。体内 switch，路由 `route_review`，统一出口 `State`。pass/insufficient_source 为空分支，显式返回本轮 while 携带值。revise/regenerate 分支为对应修订/重出包 → `apply_revision`（参考本轮 while 携带值）→ 审题包 → `merge_review`（参考该分支 `apply_revision` 输出）。分支出口选各自最后节点；while 更新携带值为该 switch 输出。
8. while 后 `finish`，作为资料充足分支最后输出；外层两个 switch 均返回完整 `Result`。
9. 在最外层请求 switch **之后**添加 `present_result`，高级参考设为空列表，作为整个服务最后一步。内部仍用 `Result` 做分支接线，对外只返回 `PublicResult`。

所有 package 节点绑定现有模型连接；块不绑定模型。建议验收时 retryLimit=0，单任务 loopLimit 至少为总题数 N + 7（解析、规划、N 次逐题生成、初审，加最多两轮修订与审题）；生成节点累计 loopLimit 至少覆盖对应题型数量，真实验收必须额外累计全部任务实际尝试次数。while 最大两轮与状态轮数检查同时限制修订。具体正式实例预算及实际调用数记录在验收报告。

任务页只需填写以下业务内容；知识库选择项由平台根据契约自动显示在下方，按名称选择即可，无需填写 ID。点击“填入服务样例”也只填充业务内容：

```json
{
  "requirement": "根据关于黑神话的材料出三道题：一道单选题、一道判断题、一道论述题。"
}
```

## 题型、数量与运行配置

可以只请求一种题型，例如“出 5 道判断题”，也可以请求“2 道单选、1 道判断、3 道论述”。同类数量合并，未请求的题型不补题；题号按题型从 1 连续编号，例如 `choice-1`、`judgment-1`、`essay-1`。零数量可省略该题型，负数量或总数为零须重新明确需求；其他题型返回 `unsupported_request`。

业务契约不设题数上限，规划、生成、审题、缺项与修订均核对本次完整请求。实际执行受 foreach 最大条数、节点/任务 loop 与 token 预算、模型输出长度及证据充分性约束；不能静默截断或谎称只支持各一道。题量支持不保证有限资料能生成任意多道不重复的合格题目。

正式实例保留的可调限额为：foreach 最大 1,000 项，生成节点调用预算 1,000，任务调用预算 1,007，任务和节点 token 预算 10,000,000，单次输出上限 8,192，最多两轮修订。运行预算不等于用户授权调用额度；验收仍须另行累计实际尝试。

页面默认检索选用最多 8 个片段、上下文最多 12,000 字符，用户只需填写需求和选择知识库。需要调整时，在业务 JSON 中增加可选 `limits`。历史初版验收使用过 30 个片段、20,000 字符，不作为当前默认值。

## 业务结果与证据

消费端读取 `result.status`；平台任务完成表示业务结果有效返回，不等于题目质量已经通过人工确认。

| 状态 | 公开结果 |
| --- | --- |
| `completed` | `{result: {status: "completed", questions: [...]}}`，数量、题型和稳定题号已校验，模型审题通过 |
| `insufficient_source` | 仅状态和原因，不返回未通过的题目 |
| `unsupported_request` | 仅状态和原因，说明不支持的需求 |
| `quality_not_met` | 仅状态和原因，表示有限修订后质量仍未达标 |

成功题目保留以下内容：

- 单选题：题号、题型、题干、四个选项、答案和解析。
- 判断题：题号、题型、题干、布尔答案、解析与错误命题纠正。
- 论述题：题号、题型、题干、参考答案、得分点及分值。

最终结果不包含 State、知识库引用、检索候选、证据片段、规划或审题历史，单题内部 evidence 也不返回。固定修订、文档版本、fragmentId、原文及审题过程保留在任务步骤、证据和搜索记录中；历史任务仍保持原返回格式。确定性核验只能证明引文属于登记证据，不能证明材料事实或答案语义正确。

考生内容不得出现内部字段名、片段哈希、文档/版本/知识库 ID；确定性检查覆盖规划考点、题干、选项、答案、解析、纠正和评分点，命中后失败，不通过删除字符伪造合格结果。审题须对照原始需求，阻断偏题、无材料依据的评分点及实质重复赋分；语义判断仍有下文所述未解决问题。修订使用同一规划和证据，不能暗中扩大检索范围。

## 检索与资源升级

正式服务使用 BGE-small-zh-v1.5（Xenova ONNX，CPU），以解析后的 topic 查询；terms 不参与语义打分。按固定 tokenizer 切分超长片段，归一化向量余弦排序取 topK，不设最低分阈值，不做词面混合或重排。Prompt 只发送选用证据，候选保留在历史；向量不跨任务持久化。相似分数不表示资料足够，技术错误仍是任务失败，不能转换为资料不足。

知识库支持 PDF/DOCX 混合原件。要让正式实例读取 PDF，须通过页面导入并替换当前默认 RAG 的列举、读取、语义检索和证据整理资源，检查参考及契约后保存新实例；不能只更改上传文件格式。读取块目前为 3.0.0，其他资源版本及依赖以 [默认资源手册](../../resources/rag/README.md) 和源码为准。读取块使用平台 OCR，需先导入并选择完整模型组合；PDF 页码保留在内部证据中。PDF 出题未完成真实模型验收，DOCX 结果不覆盖 PDF 质量。

将较早服务升级为公开返回时，在顶层请求 switch 后添加 `blocks/present_result.py`，高级参考置空，返回契约选该块的 PublicResult 并保存。内部 switch/while 保持 Result/State 契约；无需仅为输出整理升级生成和审题包。已有实例与任务不会自动改写。

## 验收边界与历史证据

- 旧固定三题版本于 2026-09-22 获人工确认；不覆盖任意题量、语义检索或公开返回的新版内容质量。
- 数量升级的四题混合及仅两道论述完成真实数量和执行验证；两道论述答案含内部哈希，原内容质量结论已纠正。
- 6.0 的三道论述真实复验触发 blocking → 定向修订 → pass；重出、修订耗尽及取消仍未真实验收。
- 7.0 的三题生成和材料外资料不足路径已真实执行，但考点重叠被审题降为 advisory，未修复，不能认定全面内容质量通过。
- 8.0 通过历史结果的真实块子进程整理、公开契约检查及正式页面保存验证；未重新运行整个出题流程，也未增加模型调用。
- 原始 AI 文稿的现实准确性、PDF 出题、复杂 OCR 版面和大规模语料质量未通过业务验收。原件及完整真实任务数据仅保留在授权本地目录。

既有 ds 累计授权上限为 100 次。最近验收记录时出题服务历史含用户任务累计 74/100 次；此后输出整理未增加调用。继续真实调用前核对实际最新历史，不将记录时点当作实时剩余额度。

| 历史阶段 | 证据 |
| --- | --- |
| 初版业务与固定三题 | [实施计划](../../docs/archive/2026-09-21/black-myth-rag-experiment-plan.md)、[20 次调用及人工确认](../../docs/archive/2026-09-21/black-myth-rag-validation.md) |
| 任意题量 | [数量验证及后续内容纠正](../../docs/archive/2026-09-22/question-counts-validation.md) |
| 内容与溯源隔离 | [修复及真实定向修订](../../docs/archive/2026-09-22/question-content-validation.md) |
| 本地语义检索 | [真实路径、累计用量和质量限制](../../docs/archive/2026-09-22/question-semantic-validation.md) |
| PDF/OCR 平台资源 | [PDF 验证](../../docs/archive/2026-09-22/knowledge-pdf-validation.md)、[OCR 验证](../../docs/archive/2026-09-22/local-ocr-validation.md) |
| 最终公开返回 | [8.0 输出整理验证](../../docs/archive/2026-09-24/question-output-validation.md) |
