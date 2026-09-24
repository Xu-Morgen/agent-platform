# 桌面管理本地 PostgreSQL

更新日期：2026-09-24。桌面默认使用应用专用 PostgreSQL，启动即持久化。数据库连接、端口和认证由程序内部生成，用户不填写数据库连接。已在 Ubuntu 24.04 / PostgreSQL 16.15 上完成真实数据库与 Electron 启停验证。

## 使用与数据位置

准备好下文所列运行程序与依赖后，按 [项目启动说明](../readme.md#启动) 启动桌面或独立 API。

Electron 使用 `app.getPath('userData')/storage`；默认 Linux 路径为：

```text
~/.config/Agent Platform/storage/
├── postgresql/       PostgreSQL 数据文件，包括 WAL 和系统目录
├── secrets.json      数据库认证及凭据加密主密钥，仅当前用户可读写
├── task-files/       上传副本与历史任务文件
├── knowledge-originals/ 知识库不可变 PDF/DOCX 原件（逻辑移除仍保留）
├── embedding-models/ 本地 embedding 不可变模型文件
├── ocr-models/       本地 OCR 不可变模型组合
├── runtimes/         独立 Python 环境、SDK、wheel 与模型缓存
├── postgresql.log    本地数据库日志
└── desktop.lock      防止两个后端管理同一个目录
```

以页面左侧显示的实际存储目录为准；`GET /api/v1/platform` 返回 `persistent=true` 和 `dataDirectory`。源码仓库、node_modules 和数据库数据目录相互独立，退出应用保留数据。

数据库运行程序安装在 `~/.local/share/agent-platform/postgresql/`，此目录不包含业务数据。当前按源码方式运行，不分发跨平台安装包；已验收 Linux，macOS 的运行程序发现与生命周期代码尚未实际验收，Windows 生命周期暂不支持。

## 新环境准备

Python 依赖统一记录在 `pyproject.toml` 和 `uv.lock`，包含 psycopg 与 cryptography。准备新环境时执行：

```bash
uv sync --frozen
npm --prefix desktop ci
```

Ubuntu 24.04 可显式执行一次用户级 PostgreSQL 安装脚本：

```bash
.venv/bin/python scripts/install_local_postgres.py
```

脚本通过系统 APT 源下载 PostgreSQL 16、客户端及 libpq 发行包，解压到用户运行程序目录，不注册系统服务、不创建系统数据库、不要求 sudo，也不会覆盖已有运行程序目录。已有系统 PostgreSQL 程序也可被发现。特殊安装路径可通过 `AGENT_PLATFORM_POSTGRES_BIN` 指定包含 postgres、initdb、pg_ctl 的目录；这只是开发部署设置，不是数据库连接配置。

正常启动不下载依赖。数据库程序缺失、密钥损坏或数据库不可用时明确报错，不退回内存。当前依赖锁定为 psycopg 3.3.5、cryptography 50.0.1；PostgreSQL 程序版本由安装时的系统发行源确定，已有数据目录必须匹配原主版本，不自动执行跨主版本升级。

独立 API 启动也默认管理相同的本地数据库；开发隔离使用 `--data-dir /absolute/path`，桌面和独立后端不能同时占用同一目录。只有显式传入 `--memory` 才启用开发用内存模式，不能与 `--data-dir` 同时使用。桌面不提供内存切换，外部传入的数据库 URL/主密钥也不覆盖其内部连接。

## 启动、退出与故障

1. 桌面单实例锁与后端目录锁阻止重复管理。
2. 首次生成随机认证和 Fernet 主密钥，通过临时文件原子保存；文件权限为 0600，存储目录为 0700。密钥缺失而数据库已存在时拒绝启动，不生成新密钥覆盖旧数据。
3. 首次 `initdb` 在临时目录初始化并原子改名。仅监听 `127.0.0.1`，使用随机空闲端口和 SCRAM 认证，不开放 Unix socket，不修改系统 PostgreSQL。
4. 等待 PostgreSQL 就绪，创建专用数据库及平台表，恢复资源、配置和记录，再启动 HTTP 与任务消费者池。启动错误返回桌面，不显示虚假的就绪。
5. 退出先中止传输、处理任务终态并关闭数据库连接，再用 PostgreSQL fast shutdown 正常停库；不关闭 fsync。
6. 桌面父进程消失时，控制管道 EOF 触发同样的退出清理。Python 本身被 SIGKILL 时数据库可能残留；下次在成功取得目录锁后只回收该目录的残留数据库，再启动恢复，不删除 PostgreSQL 的锁文件或数据。

关闭桌面不删除数据库。双后端争用、密钥错误、写入失败均明确报错；存储连接失败后拒绝后续写入和任务提交，需要重启恢复，不透明重连。

## 保存内容与事务

| 集合 | 内容与写入边界 |
| --- | --- |
| resources | 源码/Prompt 字节、摘要、类型和契约 symbol，不依赖原始文件路径，不使用 pickle |
| environments | 连接设置、名称与修订号；运行占用属于当前进程 |
| credentials | 凭据引用及 Fernet 密文；主密钥保存在数据库之外的 secrets.json |
| drafts | 可不完整的编辑草稿，不激活服务 |
| instances | 已规范化拼图、摘要和编译器版本；引用不可变资源 |
| services | 服务、当前实例指针和历史；与新实例写入同一事务，成功后才发布内存状态 |
| settings | `platform` 保存任务并发数（默认 4，重启生效）；`embedding` / `ocr` 保存默认模型选择，对后续提交立即生效 |
| task_files | 上传元数据、过期时间与任务关联；文件内容保存在 task-files/，关联与任务提交同一事务 |
| knowledge_bases / knowledge_revisions / knowledge_versions / knowledge_files | 知识库元数据、固定修订及不可变原件版本；原件在 knowledge-originals/，逻辑移除不物理回收 |
| embedding_models / ocr_models | 模型清单、身份及状态；模型文件在对应模型目录，默认选择保存在 settings，任务固定清单 |
| runs | 固定输入、版本、公开环境快照、步骤、用量、终态和结果，以及知识库绑定、证据、embedding/OCR 快照和调用记录；更新成功落库后返回 |

格式版本表为 `agent_platform_meta`，版本为 1；数据表为 `agent_platform_documents`，使用 JSONB。`DocumentStore.write` 保证批次全部提交或全部回滚。领域仓储与数据库驱动分离，业务包不访问平台内部数据库。

凭据先写密文再写环境引用；失败最多留下未引用密文，不发布悬空引用。密钥文件通过本机账户权限保护，尚未集成系统钥匙串；加密不防御已控制同一操作系统账户的进程。备份时须一并妥善保存密钥，数据库备份本身不足以恢复凭据。

## 重启后的行为

完成、失败和取消记录保持终态；遗留 queued/running（包括取消等待）标为 `failed / APPLICATION_INTERRUPTED`，运行中的步骤同步失败，释放环境占用。正常退出记录 `cancelled / APPLICATION_EXIT`。

恢复记录不重入队、不重放外部操作。历史回退使用当前环境；版本编号按已保存历史继续，资源从已保存字节加载，删除原始源码后仍可使用。

备份恢复用于还原保存的数据，不会使中断任务自动继续。产品理由见 [产品决策](product-requirements.md#明确不考虑的能力2026-09-21)，执行检查点与恢复边界见 [架构说明](architecture-design.md#12-运行与扩展边界)。

## 验证范围与维护边界

Ubuntu 24.04 的真实 PostgreSQL 与 Electron 启停、记录恢复、凭据和锁边界已验证；详细历史范围见 [验证摘录](archive/2026-09-24/manual-validation-excerpts.md#postgresql-初版验证)。这些结果不等于跨平台、业务模型或备份工具验收。

后续需补：备份恢复工具、日志与历史保留/引用安全清理、数据库迁移及跨主版本升级、平台安装包。当前启动加载全部资源和任务，分页仅限制 API 返回量；单后端进程内使用可配置的任务消费者池（默认并发 4，见 [配置说明](../readme.md#任务并发配置)），尚无多用户或大规模容量承诺。应用停止且确认数据库已关闭后可复制整个 storage 目录作离线备份；不要直接复制运行中的数据库目录作为一致性备份。

实现依据：[PostgreSQL 启停](https://www.postgresql.org/docs/current/app-pg-ctl.html)、[初始化](https://www.postgresql.org/docs/current/app-initdb.html)、[Psycopg 事务](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)、[Fernet](https://cryptography.io/en/latest/fernet/)。

## 协议与运行资产恢复

当前编译器为 flow-6。foreach 元素输出契约、switch 出口、路由和分支内资源固定在快照中；重启按原固定资源重建。旧协议历史只读及重新保存步骤统一见 [协议升级](control-flow.md#协议升级)；[flow-5 历史验证](archive/2026-09-24/manual-validation-excerpts.md#flow-5-升级验证) 不作为当前升级入口。

知识库绑定、证据、embedding/OCR 模型快照及实际调用记录随任务恢复；模型文件与原件须随完整 storage 目录一起备份。向量、推理进程及管理操作进度不作为任务续跑状态恢复；模型副本损坏时明确失败，不自动替换另一模型。分别见 [知识库](knowledge.md)、[embedding](local-embedding.md) 和 [OCR](local-ocr.md)。

flow-6 页面保存及 PostgreSQL 重启验证见 [控制流记录](archive/2026-09-21/control-flow-expansion-plan.md)；知识库、embedding 和 OCR 的独立验证见 [归档索引](archive/README.md)。
