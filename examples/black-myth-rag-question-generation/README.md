# 知识库三题出题

独立于旧全文出题实例的业务资源，首版支持单选、判断、论述各一道。根据任务固定的知识库修订检索并出题，题干限定“根据材料”；材料观点不被当作已核实的现实事实。实施历史见 [归档计划](../../docs/archive/2026-09-21/black-myth-rag-experiment-plan.md)，真实场景及用量见 [验收记录](../../docs/archive/2026-09-21/black-myth-rag-validation.md)。

## 资源与契约

`contracts.py` 是唯一契约源，使用 `sync_contracts.py` 同步到 8 个 Prompt 包和 19 个独立块；`--check` 检查副本一致性。同步工具不导入资源、不绑定环境、不创建服务。修改契约后须同步资源并升级版本，再从页面重新导入；既有实例不自动改变。

页面加载本目录 8 个包目录、`blocks/*.py`，以及默认 `resources/rag/blocks/` 中的 `list_documents.py`、`read_docx.py`、`lexical_search.py`、`select_evidence.py`。从独立 `contracts.py` 加载 `Request`、`Result`、`QuestionEnvelope`、`State`；可从资源端口选择其他契约。

## 页面拼图

所有流程在正式服务页配置；下面是操作说明，不是手写实例导入协议。普通节点默认选择高级参考空列表，只有表中列出的节点添加参考。输出来源均选对应分支最后节点。

1. 服务输入 `Request`，输出 `Result`。解析请求包 → 规范化块（参考服务输入）。
2. 请求 switch，路由 `route_request`，统一出口 `Result`。unsupported 分支为 `unsupported` 块。supported 分支继续下列步骤。
3. `prepare_retrieval` → 默认列举/读取/词面检索/整理证据四块 → 规划包（参考规范化输出）→ `merge_plan`（依次参考整理证据输出、规范化输出）。
4. 资料 switch，路由 `route_plan`，统一出口 `Result`。insufficient_source 分支为 `insufficient` 块。sufficient 分支继续。
5. foreach 从规范化节点输出选择 `items`，最大 3 项，每项出口 `QuestionEnvelope`。体内 `prepare_question`（参考 `merge_plan` 输出）→ 题型 switch（路由 `route_question`，统一出口 `QuestionEnvelope`）。single_choice/true_false/essay 各为对应生成包 → 对应 `wrap_*` 块。switch 后 `verify_question`，参考当前迭代 `prepare_question` 输出。
6. foreach 后 `collect`（参考 `merge_plan` 输出）→ 整体审题包 → `merge_review`（参考 `collect` 输出）。
7. while，条件 `needs_revision`，最多 2 轮，携带 `State`。体内 switch，路由 `route_review`，统一出口 `State`。pass/insufficient_source 为空分支，显式返回本轮 while 携带值。revise/regenerate 分支为对应修订/重出包 → `apply_revision`（参考本轮 while 携带值）→ 审题包 → `merge_review`（参考该分支 `apply_revision` 输出）。分支出口选各自最后节点；while 更新携带值为该 switch 输出。
8. while 后 `finish`，作为资料充足分支最后输出；外层两个 switch 均返回完整 `Result`。

所有 package 节点绑定现有模型连接；块不绑定模型。建议验收时 retryLimit=0，单任务 loopLimit=10（解析/规划/三次生成/初审共 6 次，最多两轮各修订与审题 2 次），真实验收必须额外累计全部任务实际尝试次数。while 最大两轮与状态轮数检查同时限制修订。具体正式实例预算及实际调用数记录在验收报告。

任务页只需填写以下业务内容；知识库选择项由平台根据契约自动显示在下方，按名称选择即可，无需填写 ID。点击“填入服务样例”也只填充业务内容：

```json
{
  "requirement": "根据关于黑神话的材料出三道题：一道单选题、一道判断题、一道论述题。"
}
```

## 业务结果与证据

消费端读取 `result.status`。`completed` 表示准确三题且审题通过；`insufficient_source` 带本次检索的缺项、范围和受限情况；`unsupported_request` 说明支持范围；`quality_not_met` 保留两轮修订后仍存在的问题和完整审查历史。平台任务完成只代表业务结果有效返回，不代表题目合格。

引用由 fragmentId 对应结果上下文里的固定知识库修订、文档版本、片段原文、摘要和段落定位。确定性检查证明引文属于登记证据，不证明材料事实或答案语义正确。单选唯一性、判断反证、论述可评分性和跨题重复仍需审题及人工核对。所有修订使用相同规划和证据，不能暗中扩大检索。

默认检索采用词面匹配；可在页面用兼容资源替换检索块并保存新实例。空检索不会生成成功空题目；技术错误保持任务失败，不转换成资料不足。原始 DOCX 与完整真实调用记录仅保存在已授权本地数据目录，不提交 Git。

## 真实验收与使用边界

正式服务“知识库三题出题 · ds”（`svc_303e8991d0124b4eb92de3fbc0b4edc3`）与“黑神话材料阅读出题”知识库已保存到桌面数据目录。页面使用契约默认检索参数（选用最多 8 个片段、上下文最多 12,000 字符），用户只需填写需求和选择知识库。历史真实验收使用 30 个片段、20,000 字符；如需调整检索范围，可在业务 JSON 中额外填写可选的 `limits`，不影响知识库控件自动补齐引用。

解析包为 1.0.0，其余业务包及全部业务块为 2.0.0。模型 Prompt 只渲染选用证据，不渲染全部候选；候选仍留在任务记录中。首次 1.0 实验发现的越界引用已被严格核验阻止，失败历史保留，未改写成成功。最终任务页独立显示原始业务状态，不把 `insufficient_source` 等业务结论当成合格题目。

真实修订、重出、修订耗尽及取消尚未在本轮远端调用中触发，只能按已记录的离线边界或既有平台验证理解；不宣称这些业务路径已经真实模型验收。AI 文稿的现实准确性、图片/OCR、复杂排版以及大规模语料不在本轮验收范围。

最终默认实例为 4.0（`ins_dc1fb98ee71f4e01bf44505fed955cc8`）。20 次 ds 调用已验证默认/替换检索主路径、不支持请求及两种资料不足；原件、知识库、服务和任务历史跨重启保留。用户于 2026-09-22 确认人工验收通过。可在任务页打开 `run_8020c33ecdfd41bfaba96d72ac75c12a` 核对三题和来源。
