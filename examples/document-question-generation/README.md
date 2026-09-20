# 文档出题与有限修订

当前资源实现“全文读取 → 规划 → 初稿 → 独立审题 → 最多两轮定向修订/重新出题 → 最终验收”。平台执行协议为 flow-5；模型仅输出声明的数据，Python 块维护原文、轮次和分支判断。实施计划已[完成归档](../../docs/archive/2026-09-20/document-question-quality-plan.md)，实际结果见[验收记录](../../docs/document-question-quality-validation.md)。真实调用仅在用户明确授权的连接和总次数范围内进行。

成功返回 `questions`，顺序固定为论述题、四选一单选题、填空题各一道。每题含稳定 `questionId`、原文 `evidence` 和参考答案；填空题另含每空的 `acceptedAnswers`。格式、引用存在性通过不代表语义或教学质量已经合格，必须经过独立审题和最终验收。

## 资源、版本与契约

| 资源 | 版本 | 职责 |
| --- | --- | --- |
| [read_document.py](read_document.py) | 3.0.0 | PDF/DOCX 全文读取并生成显式行号索引；读取算法未变 |
| [document-question-planner](document-question-planner/package.json) | 2.0.0 | 判断资料充分性，规划三个考点、目标、难度、依据 |
| [document-question-generator](document-question-generator/package.json) | 4.0.0 | 初稿和重新出题共用包，独立节点配置 |
| [document-question-reviewer](document-question-reviewer/package.json) | 2.0.0 | 独立审题，逐题 findings 和总体 verdict |
| [document-question-reviser](document-question-reviser/package.json) | 2.0.0 | 只修订被 findings 指出的题目 |
| [quality-blocks](quality-blocks/) | 每块 2.0.0 | 规划核验、输入转换、状态维护、条件、最终验收 |
| [quality_contracts.py](quality_contracts.py) | 源码随资源版本固定 | 权威契约和确定性规则 |
| [quality-schemas.json](quality-schemas.json)、[contract-examples.json](contract-examples.json) | 派生交付说明 | 公开 Schema 与通过权威契约校验的合成示例 |

入口均为 `NodeInput[P, tuple[...]]`。服务调用者只提交业务数据。所有模型使用 StrictModel，不接受额外字段或隐式类型转换。读取块输入为 `{document: TaskFile}`，输出为 `{fileName, text, numberedText}`；任务页上传文件后获得真正的 TaskFile，不能使用占位引用。

单文件块快照不能相对导入外部业务文件，因此资源中嵌入生成的契约。只编辑 `quality_contracts.py`，再在仓库根目录运行：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python examples/document-question-generation/sync_contracts.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python examples/document-question-generation/sync_contracts.py --check
```

该工具只同步契约源码/Schema 和核验公开示例，不加载服务、安装依赖、创建实例或访问模型。修改共享契约会改变所有嵌入资源的内容，发布前逐一递增受影响包/块版本并重新加载，不能以原版本覆盖已有快照。

消费端声明完整结构类型；模型输出端的 GeneratedQuestions/ReviewResult 额外执行题序、选项唯一、填空对应、审题覆盖及 pass/阻断矛盾校验。自定义 validator 不能跨资源假称同一契约身份；Python 状态块再次执行关系校验和依据检查，最终服务输出直接选择 finalize_questions 的出口契约。

## 状态与错误边界

QuestionState 必须含 document、已确认 sufficient 的 plan、current、review 和 revisionRounds。review 使用 `awaiting_review`/`reviewed` 严格联合，缺失审题不以 null 或空字典表示。模型不能输出原文副本或改轮数；每次状态更新从可信参考恢复资料和规划，Python 增加轮数。

读取块保留原始 text，并由 Python 生成 numberedText（`行号: 原始行内容`，空行也编号）。模型直接读取编号填写 Evidence.startLine/endLine，不根据 JSON 排版、展示换行或 PDF 页码自行数行。quote 不含编号前缀，仍必须逐字存在于原始 text 的声明范围；Python 同时核对编号索引与正文一致性。PDF 原页码保留在正文中，DOCX 行定位不等于页码。Python 检查存在性，审题模型检查语义支持。审题 findings 必须引用三题中的 ID；跨题问题分别记录。

| 情况 | 平台结果 |
| --- | --- |
| 规划 insufficient_source 或最终审题 insufficient_source | PACKAGE_INPUT_INSUFFICIENT，明确失败 |
| 模型保留对象 `{"error":"INSUFFICIENT_INPUT"}` | 平台失败协议，不作为业务状态或成功题目 |
| 非法枚举、题目格式错误、pass 同时携带 blocking | OUTPUT_VALIDATION_ERROR，按 retryLimit 重试该生产包 |
| 无效原文引用、规划顺序/考点重复、非法状态、定向修订改动无关题目 | CONTRACT_VALIDATION_ERROR，立即终止，不让模型 pass 覆盖 |
| 两轮后仍 revise/regenerate | LOOP_ITERATION_LIMIT，不返回未通过题目 |
| 未审或非 pass 状态进入最终验收 | 明确失败，不把 while 停止视为成功 |

## 服务页拼接

通过平台页面加载上表所有包/块。服务输入选读取块 primaryContract，返回选 finalize_questions outputContract。下表节点 ID 为操作说明，均可在服务页填写；不提供另一套流程导入文件或长期自动组装脚本。

| 顺序/位置 | 节点 ID → 资源 | 参考配置（高级列表按位置填写） |
| --- | --- | --- |
| 顶层 1 | read → read_document | 简单，首步零参考 |
| 顶层 2 | plan → document-question-planner | 高级空列表 |
| 顶层 3 | verify → verify_plan | 简单：规划包当次 primary，即全文 |
| 顶层 4 | prepare → prepare_generation | 高级空列表 |
| 顶层 5 | draft → document-question-generator | 高级：read 完整输出、verify 完整输出 |
| 顶层 6 | init → initialize_state | 高级：read 完整输出、verify 完整输出 |
| 顶层 7 | review → document-question-reviewer | 高级空列表 |
| 顶层 8 | merge → merge_review | 简单：审题当次完整状态 |
| 顶层 9 | revisions → while | maxIterations=2；见下方 |
| 顶层 10 | final → finalize_questions | 高级空列表 |

while 的 carry.contract 选 init 的出口；initial 引 merge 完整输出；update 引循环体末尾 merge_again 完整输出。条件 continue 使用 needs_revision，高级空参考。while 内部依次为 strategy（if）、review_again（审题包，高级空参考）、merge_again（合并块，简单参考）。

if 条件 regenerate_condition 使用 needs_regeneration，高级空参考；if 输出契约选择 init 出口。两个分支：

| 分支 | 节点序列 | 分支出口 |
| --- | --- | --- |
| then：重新出题 | prepare_again（prepare_generation，高级空参考）→ regenerate（出题包，高级参考 read、verify）→ update_regenerated（update_regeneration，简单参考） | update_regenerated 完整输出 |
| else：定向修订 | revise（修订包，高级空参考）→ update_revised（update_revision，简单参考） | update_revised 完整输出 |

prepare_generation 是显式转换块：把初稿的规划或重新出题的完整状态封装为 GenerationInput，让同一出题包用于两个独立节点。update_regeneration 的默认参考是该包当次 GenerationInput，块从 context 取原状态；update_revision 默认参考是原 QuestionState。两个分支出口和循环 carry 均为 QuestionState。不得从循环外引用内部节点或上一轮残留。

## 模型连接和预算

包节点独立绑定连接，审题节点可另选模型；同模型独立调用可作为首版，不代表独立人工评审。将完整正文发送给绑定的模型服务商。无需在本机运行大语言模型。

正式使用可从 retryLimit=2、任务 loopLimit=21、tokenLimit=524288 开始；规划/初稿/首次审题各节点 loopLimit=3，循环内重出题/修订/再审各节点 loopLimit=6，节点 tokenLimit=262144；maxOutputTokens=8192。这些是可调整的操作起点，不是费用或容量保证。7×(retryLimit+1)=21 为最长技术尝试规划上界；互斥分支的节点预算不能当作全局额度相加。

本次真实验收按用户限制使用 ds，所有基线、失败尝试和质量路径合计最多 10 次；retryLimit=0，while 上限仍为 2，实际配置与计量以验收记录为准。包清单 budgetDefaults 只作初始化建议，服务页按单次或重复节点分别调整。

模型上下文容量和累计任务预算不同。平台按供应商 usage 记账，未知用量明确失败，不用文档字符数估算精确 token。正文不截断、分块或摘要，超出上下文应换连接或较小完整资料。取消、关闭应用与 APPLICATION_INTERRUPTED 沿用平台语义。

## 准备与运行限制

声明固定版本：rapidocr-onnxruntime 1.4.4、onnxruntime 1.23.2、PyMuPDF 1.26.7、python-docx 1.2.0，索引为 `https://pypi.org/simple`。平台准备独立环境并锁定传递依赖；不在任务函数安装库。OCR 三个模型的固定 URL、版本和 SHA-256 已写入 @block 字面量，来源为 [RapidAI 官方模型清单](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)。不要修改为无摘要的下载地址。

引擎只接收 context.model 提供的本地 det/rec/cls 路径；一个工作进程内复用，不逐页初始化。平台每次块调用创建独立工作进程，不跨任务缓存引擎。

| 限制 | 行为 |
| --- | --- |
| 文件 50 MiB；DOCX 解压总量 100 MiB | 超限失败，不只取前部内容 |
| PDF 打开密码 | 无需密码即可打开的权限加密文件可读取；需要打开密码时明确拒绝 |
| PDF 1～100 页 | 超限失败，不丢弃剩余页 |
| 144 DPI；单边 6000 像素、单页 2000 万像素 | 超限失败，不悄悄降采样 |
| 读取 240 秒；平台进程 300 秒 | 逐页/段落检查期限，平台可终止卡住的计算 |
| OCR 行置信度低于 0.5、无可识别结果 | 明确带页码失败，不冒充完整正文 |
| DOCX 图片、公式、嵌入对象、脚注、修订、内容控件等 | 明确失败，建议先转 PDF；不静默漏读 |

纯文字 PDF 直接提取；显示图片、矢量内容、异常字符或无文字层的页面整页 OCR，替换该页文字层以避免重复。PDF 按页面渲染方向识别，关闭 OCR 文本行的自动 180° 方向分类，避免把正常长行误翻转；文件自带的页面旋转由渲染器处理，页面中实际倒置的扫描文字需要先校正方向。RapidOCR 1.4.4 初始化仍需要 cls 模型，因此保留声明与校验，但 PDF 识别不执行分类器。OCR 空识别框仅在框内像素确认为空白时忽略（检查时向内收 1 像素，避免边缘擦到相邻字形）；有内容的低置信度结果仍报错。OCR 按几何位置组织基本阅读顺序，复杂表格/双栏/倾斜/低清晰度仍需人工核对，置信度不能证明没有漏字。DOCX 按 [python-docx 文档顺序接口](https://python-docx.readthedocs.io/en/latest/api/document.html#docx.document.Document.iter_inner_content)读取段落与表格；正文不包括页眉页脚。

取消由平台父进程持续检查并终止本地工作进程；用户在模型调用中取消仍沿用“等当前请求结束”的语义。任何页面失败都不发布已提取的部分正文为成功结果。

## 验收范围

实现后的离线验证覆盖首轮 pass、定向修订、重新出题、两轮混合、达到上限、资料不足、非法引用/ID、矛盾 pass 和技术重试计数。替身只验证协议和确定性规则，不证明真实出题质量。

真实验收采用自制 DOCX、现有 ds 连接，对照旧一次出题基线，并保存实际模型响应、计量和流程终态；共完成 10 次调用，实际发生一次定向修订，最终流程通过；详见[验收记录](../../docs/document-question-quality-validation.md)。用户已确认人工评审通过；随后通过实际 Electron 页面保存正式服务“文档出题质量 · ds”（版本 1.0，serviceId=svc_e8c711863f8a4e54a197f60d2b55913d），重启后恢复及预检通过。正式实例未额外调用模型。其配置为 retryLimit=0、任务 loopLimit=7/tokenLimit=524288，单次节点 loopLimit=1、重复节点 loopLimit=2。新建其他服务可按上述步骤配置。

历史 OCR 验证仍见[文档验收记录](../../docs/archive/2026-09-20/document-validation-record.md)。此前《从市场营销到社会营销》两页读取通过；另一份保险商业智能 PDF 的空识别框仍明确失败，复杂表格、双栏、倾斜和低清晰度资料未完成质量验收。本轮不扩大读取范围，也不把简单文档成功解释为复杂 OCR 已通过。

## 行号引用修复（2026-09-20）

真实长文任务曾在 node_6 失败：两道题引用了原文真实存在的句子，但把它们指向第 84 行（该行实际是标题）。初版 Prompt 要求模型对未编号的全文自行数行，短文验收没有暴露这个问题。当前版本增加显式编号，优先复用规划中已经核验的依据；错误会给出题目 ID、第几条依据、声明范围和 fieldPath，不再只有通用提示。

不搜索全文后自动重定位错误引文，不放宽逐字匹配，不静默修改失败任务。新增 numberedText 属于资源契约升级，读取块、四个包及九个质量块须成套重新加载并保存新实例；单改源码不会改变现有快照。通用 samples 无需加入此业务字段。

当前“文档出题质量 · ds”已通过实际服务页升级到版本 **2.0**，实例 `ins_3a0741d599264b14b9f6e303f8b64ac5`，参考配置、ds 连接、任务预算和 retryLimit 保持原值。新提交使用新实例，历史失败任务保持原记录。此次修复只做历史数据离线复现、资源/接线与页面校验，未追加线上调用，尚未进行新版本真实模型再验收。显式编号降低数行错误，但不保证模型永远不会引用错误；严格校验仍会拒绝不正确的依据。
