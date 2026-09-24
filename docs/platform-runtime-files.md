# 平台运行文件与依赖

核对日期：2026-09-24。三类业务资源不变；任务文件、依赖环境、模型缓存均为平台运行数据。当前实现面向 Linux/macOS 的受信任本地块，不提供代码沙箱或系统库安装。

## 静态声明

`@block` 的所有参数必须直接使用字面量，不能通过变量、函数调用、`**kwargs` 获取声明。平台先读 AST，再准备环境，最后在对应 Python 子进程中导入文件。只有一个顶层注册函数；平台会比对导入后的元数据与静态声明。

| 字段 | 定义 |
| --- | --- |
| `dependencies` | PEP 508 包版本约束列表；支持 extras 和环境标记；正式交付固定经过验证的版本 |
| `dependencySources` | `{"kind":"index","url":"https://pypi.org/simple"}`，或 `{"kind":"wheel","package":"包名","url":"固定 wheel URL","sha256":"64 位小写摘要"}` |
| `models` | `{"name":"模型标识","version":"模型版本","url":"固定 HTTPS URL","sha256":"64 位小写摘要","filename":"单个文件名"}` |

PEP 508 依赖列表不直接填写 URL，指定下载源使用 dependencySources。最多一个索引源；默认 PyPI。模型名称及 wheel 包名不能重复；wheel 来源须对应直接声明的包。URL 禁止明文 HTTP、凭据、查询参数和 fragment，当前不支持私有下载凭据。模型按独立文件保存，不自动解压。模型地址和摘要必须核对发布者来源，不能以占位摘要作为可运行示例。

模型 `name` 以英文字母开头，仅含字母、数字、下划线、连字符；`sha256` 为实际文件的 64 位小写摘要，`filename` 为不含目录的单个文件名。运行时按 name 访问模型文件，多个文件分别声明。

权威定义为 `contracts/dependencies.py` 和 `blocks/single.py`，公开 Schema 由 `scripts/export_contracts.py` 生成。模板见 [完整块](../samples/blocks/complete.py)。

## 环境、缓存及运行

声明第三方依赖的块使用独立 venv，平台不向主程序环境安装业务依赖。优先使用 Python `venv`/`ensurepip`；缺失时使用项目已有的 uv 为独立环境准备 pip，种子缓存保存在运行目录。两者均不可用时明确失败，不自动安装系统组件。无额外依赖的块使用平台 SDK Python 的独立子进程，无需下载基础库。

解析使用 pip 的 `--dry-run --ignore-installed --report --only-binary=:all:`，锁定直接及传递依赖的版本、制品地址与 SHA-256。平台随后下载并验证每个 wheel，以 `--no-index --require-hashes` 安装，运行 `pip check`；不接受源码构建或安装脚本。依据：[pip 安装报告](https://pip.pypa.io/en/stable/reference/installation-report/)、[摘要校验安装](https://pip.pypa.io/en/stable/topics/secure-installs/)。

环境身份包括 Python 运行时、系统/架构、SDK 及依赖锁。资源记录和实例记录保存锁，SDK 源码按摘要保留副本。旧实例引用的环境、SDK 和模型不自动清理；新资源不会原地升级旧环境。SDK 基础依赖或 Python 不兼容时明确拒绝恢复。缺失的历史 SDK 需恢复对应版本，不能用新版本冒充。

默认目录为平台数据目录下 `runtimes/`；可用 `AGENT_PLATFORM_RUNTIME_DIR` 指定验收缓存目录。模型和 wheel 按 SHA-256 缓存；临时下载校验后原子启用，读取缓存时验证模型内容，损坏后重新下载。跨进程文件锁串行化同一缓存的准备操作。完整环境和模型缓存可离线复用；缓存缺失时报告网络失败及缺项所在准备阶段。

页面通过 `/api/v1/preparations` 发起准备，轮询状态，可取消或重新加载重试。状态显示检查、下载、安装、验证、就绪及失败；仅展示实际已下载字节和服务器提供的总量。默认连接超时 10 秒、读取超时 30 秒、整体准备超时 600 秒；取消在锁等待、子进程轮询或下载分块处生效，网络阻塞等待最多受读取超时限制。准备不计业务 loop，不消耗契约失败重试。

执行使用版本 1 JSON 行协议，stdout 专用于协议；源码打印不进入协议。契约导出、真实 Pydantic 自定义校验和业务调用在对应环境执行，主平台继续做静态兼容检查。每次调用创建新进程，不保证全局变量跨调用保留。

业务执行阶段整体上限为 300 秒，包含块内计算及所有 API、OCR、embedding 等代理等待，不包含此前的环境准备。单次 API 请求另受连接 timeoutSeconds 限制；连接超时或块剩余整体时限先到者生效。整体超时报 BLOCK_TIMEOUT，取消通信并终止子进程，即使连接超时配置更长也不会继续等待。主动取消本地计算会终止子进程；API 在途时等该请求返回、超时或失败，期间整体时限继续计时。应用退出立即中止本地传输。API 由父进程转发，凭据不发给子进程；终态优先级见 [状态机](architecture-design.md#8-状态机取消与退出)。

强制终止子进程不保证执行资源代码的 `finally`，也不撤销已完成的外部操作。资源钩子及开发时的清理写法见 [研发手册](external-development-guide.md#7-第三方依赖与运行生命周期)。

## 文件输入与受控上下文

资源用 `TaskFile` 声明附件，通过 `context.file(reference)` 读取当前任务副本。公开方法和可直接加载的文件块示例见 [研发手册](external-development-guide.md#41-可直接加载的文件块)，本节维护上传、保存和清理规则。

`TaskFile` 导出 `x-platform-file` 标注，页面根据标注生成 PDF/DOCX 控件。输入契约仅包含文件字段（含固定嵌套对象）时，只显示文件控件，自动组装提交数据，隐藏 JSON 编辑区与样例按钮。包含其他字段、可空分支或数组结构时保留 JSON 输入；嵌套对象、可空字段和 JSON 中已有的数组项均支持。保存成功才允许提交，平台生成包含 `fileId`、`originalName`、`format`、`size`、`sha256` 的引用。字段内无本机路径。

页面文件控件选择本地文件，preload 从 File 对象取得路径，桌面主进程流式发送给后端，不把二进制放进 IPC JSON。取消选择保留已有附件，成功保存后显示文件名与大小；上传失败明确报错。API 客户端使用 `POST /api/v1/files?name=example.pdf`，请求体为原始文件流，响应为同一文件引用；`DELETE /api/v1/files/{fileId}` 仅删除未绑定任务的上传。

默认单文件上限 50 MiB，可通过 `AGENT_PLATFORM_FILE_MAX_BYTES` 设置。平台检查文件名、扩展名、PDF 标识或 DOCX ZIP 结构、大小与摘要；具体解析块仍须检查文件损坏、加密及业务可读性。任务提交时验证引用与实际副本，并在同一文档事务中保存任务关联。执行时只提供属于该任务且摘要正确的副本。源文件移动不影响平台副本。

未提交上传 24 小时后过期，启动时清理过期记录对应文件、失败上传临时文件及孤立文件；运行期间过期引用拒绝提交。历史任务文件不自动删除。内存模式的文件为临时会话数据；持久模式写入数据目录 `task-files/`。

任务函数不得安装依赖或自行下载模型，已准备路径按只读约定使用；受信任代码接口不构成文件系统权限沙箱。`context.model` 和 `context.progress` 的调用方式见 [研发手册](external-development-guide.md#4-context文件本地模型进度)。

## 验证与恢复边界

文件、缓存、子进程与桌面控件的历史验证结果见 [归档记录](archive/2026-09-20/document-validation-record.md)，文档业务使用 [正式读取块与出题包](../examples/document-question-generation/README.md)。

对于改造前未记录依赖锁的持久资源，首次成功恢复会补全当前经过验证的环境锁；原实例内容摘要、版本、任务历史保持原身份，之后继续使用固定锁。平台无法追溯从未记录过的历史安装状态。

原生系统文件对话框与完整桌面操作仍待人工走查；控件逻辑验证不替代此项验收。

## 知识库原件与任务文件的区别

TaskFile 绑定单次任务；跨任务文档使用知识库管理及 `TaskKnowledge` 标准引用。提交任务时固定修订，通用块通过异步方法读取和登记证据（方法名为 `knowledge_resolve`、`knowledge_list`、`knowledge_metadata`、`knowledge_file`、`knowledge_record`）。这些访问由父进程代理，不注入数据库或密钥。`knowledge_file` 返回当前块调用的临时副本路径，按只读约定使用；调用退出即清理，原件不会交给块直接修改。完整契约和上限见[知识库接口](knowledge-api.md)。

## 平台本地 embedding

设置页导入的语义模型不使用块固定依赖的 `@block(models=...)` 路径，也不进入聊天连接列表。平台 CPU 适配器和工作进程由项目固定依赖提供，任务只固定内容身份；模型文件持久化、向量仅任务内存。普通块声明 `semanticSearch=True` 后通过 context 使用，详见 [模型说明](local-embedding.md)。

## 平台本地 OCR

新版文档读取块使用平台设置导入和选择的 OCR 模型组合，以 `ocr=True` 声明能力并调用异步 `context.ocr(...)`。平台固定任务模型、管理推理进程并保存识别记录；块保留文档处理策略。旧块的 `models` 依赖机制仍供固定依赖及历史快照使用，不静默迁移。见 [OCR 管理与接口](local-ocr.md)。
