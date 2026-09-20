# 文档出题实例

每次保存一份 PDF 或 DOCX，执行“读取完整文档 → 出题包”，成功时返回论述题、四选一单选题、填空题各一道及参考答案。扫描 PDF 在本地用 RapidOCR 识别；正文一次性传给包，不逐页出题。旧版 DOC 不支持。

本次按用户要求暂不调用线上模型。已交付源码、契约、服务页配置说明并完成本地离线验收；离线模型响应只验证平台协议与重试，不能证明真实题目质量。真实模型业务验收仍需配置连接后进行。

## 资源与契约

| 文件 | 用途 |
| --- | --- |
| [read_document.py](read_document.py) | 唯一通用块；文件输入、资料输出及全部读取逻辑 |
| [document-question-generator/](document-question-generator/package.json) | 声明式业务包，只含清单、契约、Prompt |
| [contract-examples.json](contract-examples.json) | 文件引用、资料、合法题目及非法题目示例 |

文件输入为 `{document: TaskFile}`，使用平台已有格式限制和文件控件。示例中的零值摘要和 ID 只演示结构，不能作为实际任务输入；必须先由任务页或上传接口获得引用。

资料为 `{fileName, text}`，两项均非空且非纯空白。读取块出口与包入口独立声明兼容结构；路径与 OCR 模型信息不进入资料。PDF 保留原始页码，空白页进度单独记录；DOCX 没有伪造分页。

题目输出固定为 `{questions: [...]}`，题型顺序由 Python 校验，Schema 的 minItems/maxItems/prefixItems 同步表达。选项为严格 A/B/C/D 对象，文本去除无关空白并忽略大小写比较后不能重复。填空标记只能是四个连续下划线，每空对应一个非空答案。所有模型继承 StrictModel，禁止未知字段和隐式转换。

服务端口直接使用块/包加载后提供的 inputContract/outputContract。可单独加载 read_document.py 的 Input/Output、包 models.py 的 Input/Output 查看契约；自定义题目校验依赖契约身份，服务返回应选择包自己的输出契约，不以另载文件的相似 Schema 代替。

| 契约用途 | Python 文件 | 加载时填写的 symbol |
| --- | --- | --- |
| 文件输入 | [read_document.py](read_document.py) | Input |
| 全文资料（读取块输出） | [read_document.py](read_document.py) | Output |
| 全文资料（业务包输入） | [models.py](document-question-generator/models.py) | Input |
| 三种题目与参考答案 | [models.py](document-question-generator/models.py) | Output |

## 准备与运行限制

声明固定版本：rapidocr-onnxruntime 1.4.4、onnxruntime 1.23.2、PyMuPDF 1.26.7、python-docx 1.2.0，索引为 `https://pypi.org/simple`。平台准备独立环境并锁定传递依赖；不在任务函数安装库。OCR 三个模型的固定 URL、版本和 SHA-256 已写入 @block 字面量，来源为 [RapidAI 官方模型清单](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)。不要修改为无摘要的下载地址。

引擎只接收 context.model 提供的本地 det/rec/cls 路径；一个工作进程内复用，不逐页初始化。平台每次块调用创建独立工作进程，不跨任务缓存引擎。

| 限制 | 行为 |
| --- | --- |
| 文件 50 MiB；DOCX 解压总量 100 MiB | 超限失败，不只取前部内容 |
| PDF 1～100 页 | 超限失败，不丢弃剩余页 |
| 144 DPI；单边 6000 像素、单页 2000 万像素 | 超限失败，不悄悄降采样 |
| 读取 240 秒；平台进程 300 秒 | 逐页/段落检查期限，平台可终止卡住的计算 |
| OCR 行置信度低于 0.5、无可识别结果 | 明确带页码失败，不冒充完整正文 |
| DOCX 图片、公式、嵌入对象、脚注、修订、内容控件等 | 明确失败，建议先转 PDF；不静默漏读 |

纯文字 PDF 直接提取；显示图片、矢量内容、异常字符或无文字层的页面整页 OCR，替换该页文字层以避免重复。OCR 按几何位置组织基本阅读顺序，复杂表格/双栏/倾斜/低清晰度仍需人工核对，置信度不能证明没有漏字。DOCX 按 [python-docx 文档顺序接口](https://python-docx.readthedocs.io/en/latest/api/document.html#docx.document.Document.iter_inner_content)读取段落与表格；正文不包括页眉页脚。

取消由平台父进程持续检查并终止本地工作进程；用户在模型调用中取消仍沿用“等当前请求结束”的语义。任何页面失败都不发布已提取的部分正文为成功结果。

## 在任务页调用

1. 环境页配置模型连接，或使用已有连接。只获取模型列表不会执行出题；“测试连接”会发送模型请求并可能计费。暂不调用模型时跳过测试和提交任务。
2. 服务页加载 read_document.py，等待依赖和模型准备完成；再加载 document-question-generator 目录。
3. “开始”选择读取块输入契约；先添加读取块，再添加出题包。普通节点接收上一层完整输出，没有字段映射或数据来源配置。
4. 包节点选择模型连接；初始输出额度 4096，节点和任务各 loopLimit=3、tokenLimit=131072，服务 retryLimit=2。返回只选择包输出契约，静态校验通过后保存实例。
5. 任务页选择文件，等到显示保存成功后提交。查看读取步骤页数进度、出题步骤和最终 questions。文件/页码错误与出题失败会分别定位。
6. 每个任务固定实例版本和文件副本。移动原文件不影响任务；持久化模式保留跨重启历史，`--memory` 模式仅供会话验证。

## 线上模型与 DeepSeek

可以采用“本地解析/OCR + 线上 API 出题”：不需要在本机运行大语言模型，出题时会把文件名与全文发送给服务商。当前平台支持 OpenAI 兼容 Chat Completions，不会把 PDF 原文件直接传给多模态接口。

截至 2026-09-20 核对的 [DeepSeek 官方模型表](https://api-docs.deepseek.com/quick_start/pricing/)，当前模型名为 deepseek-flash、deepseek-v4-pro，标注上下文为 1M。以账户实时获取的列表和官方定义为准，避免硬编码旧模型名。线上模型并非已经在本项目实测通过。

| 平台设置 | DeepSeek 配置 |
| --- | --- |
| kind | model |
| baseUrl | `https://api.deepseek.com`（平台追加 /chat/completions） |
| model | 从“获取模型”结果选择，例如 deepseek-flash |
| credential | 在环境页填写自己的 API Key，不写入包或示例文件 |
| outputTokenParameter | max_tokens |
| jsonMode | true |
| timeoutSeconds | 可从 180 开始，长文按实际调用调整 |

[DeepSeek Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)定义了 max_tokens 和 JSON output；当前桌面在输入 api.deepseek.com 地址时已自动选择 max_tokens。其他兼容服务的该参数可通过环境 HTTP API 显式配置。DeepSeek 当前默认思考模式，4096 输出额度可能包含思考消耗；若 finish_reason=length，需要增大包节点 maxOutputTokens 和相应预算。平台不会将截断响应作为成功题目，也不会静默改用其他模型。

平台当前没有统一 tokenizer/模型容量目录，因此不使用字符数估算 token，不宣称做了精确容量预检。全文、Prompt、输出额度均计入模型容量；供应商明确的上下文超限机器码转为 MODEL_CONTEXT_EXCEEDED，其他格式保留 HTTP 状态和传输错误。出现超限请选择容量更大的模型或更小的完整文档；不自动截断、摘要、分块或重做 OCR。

预算是累计供应商实际 token 的上限，不是模型上下文容量，也不等于人民币费用。131072 的初始预算无法覆盖 1M 上下文的满量请求；长文需相应提高节点和任务预算，并为最多三次包调用留余量。没有可用 usage 时平台明确失败。资料不足时包返回保留对象 `{"error":"INSUFFICIENT_INPUT"}`，平台记账后以 PACKAGE_INPUT_INSUFFICIENT 终止；它不是成功题目且不触发格式重试。

## 验证与待办

历史本地 OCR 与任务链路验收见[归档记录](../../docs/archive/2026-09-20/document-validation-record.md)。开发验收脚本、样本生成器及回归测试已按项目规则删除；服务组装辅助脚本也已清理，服务统一通过平台页面配置；业务包、读取块与契约示例继续保留。

正式服务尚未绑定用户选定的模型连接。真实线上出题、答案正确性、单选唯一性、复杂排版/低清晰度资料质量及桌面人工走查仍待验收，按用户要求暂不调用线上模型。后续配置模型连接、保存正式服务，再使用自制或授权文档逐项核对；JSON 合法不能代替业务验收。
