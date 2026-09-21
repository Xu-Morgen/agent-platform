# 桌面管理本地 PostgreSQL

更新日期：2026-09-21。桌面默认使用应用专用 PostgreSQL，启动即持久化。数据库连接、端口和认证由程序内部生成，用户不填写数据库连接。已在 Ubuntu 24.04 / PostgreSQL 16.15 上完成真实数据库与 Electron 启停验证。

## 使用与数据位置

当前工作环境已安装所需运行程序与 Python 依赖，直接运行：

```bash
env -u ELECTRON_RUN_AS_NODE npm --prefix desktop start
```

Electron 使用 `app.getPath('userData')/storage`；默认 Linux 路径为：

```text
~/.config/Agent Platform/storage/
├── postgresql/       PostgreSQL 数据文件，包括 WAL 和系统目录
├── secrets.json      数据库认证及凭据加密主密钥，仅当前用户可读写
├── task-files/       上传副本与历史任务文件
├── knowledge-originals/ 知识库不可变 DOCX 原件（逻辑移除仍保留）
├── runtimes/         独立 Python 环境、SDK、wheel 与模型缓存
├── postgresql.log    本地数据库日志
└── desktop.lock      防止两个后端管理同一个目录
```

本机实际数据库目录为 `/home/nemo/.config/Agent Platform/storage/postgresql/`。页面左侧显示当前存储目录；`GET /api/v1/platform` 返回 `persistent=true` 和 `dataDirectory`。源码仓库、node_modules 和数据库数据目录相互独立，退出应用保留数据。

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

独立 API 启动也默认管理相同的本地数据库：

```bash
.venv/bin/python -m agent_platform --host 127.0.0.1 --port 8000
```

开发隔离使用 `--data-dir /absolute/path`；桌面和独立后端不能同时占用同一目录。只有显式传入 `--memory` 才启用开发用内存模式，不能与 `--data-dir` 同时使用。桌面不提供内存切换，外部传入的数据库 URL/主密钥也不覆盖其内部连接。

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
| settings | `platform` 记录保存全局任务并发数；首次补齐默认值 4，保存落库后返回，下次后端启动时应用 |
| task_files | 上传元数据、过期时间与任务关联；文件内容保存在 task-files/，关联与任务提交同一事务 |
| runs | 固定输入、版本、公开环境快照、步骤、用量、终态和结果；更新成功落库后返回 |

格式版本表为 `agent_platform_meta`，版本为 1；数据表为 `agent_platform_documents`，使用 JSONB。`DocumentStore.write` 保证批次全部提交或全部回滚。领域仓储与数据库驱动分离，业务包不访问平台内部数据库。

凭据先写密文再写环境引用；失败最多留下未引用密文，不发布悬空引用。密钥文件通过本机账户权限保护，尚未集成系统钥匙串；加密不防御已控制同一操作系统账户的进程。备份时须一并妥善保存密钥，数据库备份本身不足以恢复凭据。

## 重启后的行为

完成、失败和取消记录保持终态；遗留 queued/running（包括取消等待）标为 `failed / APPLICATION_INTERRUPTED`，运行中的步骤同步失败，释放环境占用。正常退出记录 `cancelled / APPLICATION_EXIT`。

恢复记录不重入队、不重放外部操作。历史回退使用当前环境；版本编号按已保存历史继续，资源从已保存字节加载，删除原始源码后仍可使用。

LangGraph 继续执行配置者定义的图，当前 `checkpointer=None`。平台数据持久化用于保存配置与历史；按用户明确决定，不考虑断点续跑，不建设 LangGraph 执行检查点或暂停恢复。长期记忆也不在当前交付范围。模型仍只输出严格契约内的数据，分支和循环条件由脚本块判断。

任务历史和步骤结果没有构成可原子恢复的图执行检查点；从记录推断下一步也不能保证循环状态、预算和外部副作用一致。当前出题等小任务不引入这套恢复复杂度，具体取舍见 [产品决策](product-requirements.md#明确不考虑的能力2026-09-21) 与 [执行恢复边界](architecture-design.md#122-记录持久化不扩展为执行恢复)。备份恢复用于还原保存的数据，不会使中断任务自动继续。

## 验证范围与维护边界

以下为历史验证结果。对应开发测试及回归测试已按 [AGENTS.md](../AGENTS.md) 规则删除，不再提供运行命令。

10 项 Python 检查（5 项为真实 PostgreSQL 集成）及 4 项桌面后端生命周期检查通过，覆盖：

- 重启后恢复草稿、凭据、源码、版本及任务；源文件删除后执行。
- 历史回退、编号连续、任务结果及中断记录保留。
- 密文存储、错误/缺失密钥拒绝启动，原数据不被覆盖。
- 批次事务回滚、断连拒绝写入、目录锁及数据库锁互斥。
- 正常退出停库、启动中关闭、Python 强制终止后再次启动恢复、桌面父进程消失后的清理。

另已启动实际 Electron 窗口，确认页面就绪、显示本地 PostgreSQL 和实际数据目录，关闭后数据库进程退出。验证未调用真实模型或外部业务 API。

后续需补：备份恢复工具、日志与历史保留/引用安全清理、数据库迁移及跨主版本升级、平台安装包。当前启动加载全部资源和任务，分页仅限制 API 返回量；单后端进程内使用可配置的任务消费者池（默认并发 4，见 [配置说明](../readme.md#任务并发配置)），尚无多用户或大规模容量承诺。应用停止且确认数据库已关闭后可复制整个 storage 目录作离线备份；不要直接复制运行中的数据库目录作为一致性备份。

实现依据：[PostgreSQL 启停](https://www.postgresql.org/docs/current/app-pg-ctl.html)、[初始化](https://www.postgresql.org/docs/current/app-initdb.html)、[Psycopg 事务](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)、[Fernet](https://cryptography.io/en/latest/fernet/)。

## flow-5 协议升级（历史记录）

恢复时先检查 compilerVersion；旧实例保留原始 flow 和摘要，不用新协议解析，也不阻止历史列表或数据库启动。旧版本禁止执行与回退，页面提示重新加载升级资源并保存新实例；新实例包含 NodeInput 声明、参考模式与完整条件源码的资源快照。2026-09-20 在隔离 PostgreSQL 16 数据目录验证了新快照运行、停库重启、源码字节恢复、旧历史只读与升级保存，原历史文档保持不变。块验证使用已有 Python 环境及真实子进程通信，没有重新安装依赖。


## flow-6 控制流协议升级

当前编译器为 `flow-6`，新增 foreach 与 switch。foreach 元素输出契约、switch 统一输出契约以及所有循环体/路由块/分支内资源都固定在快照中；集合 Schema 由元素契约派生，重启时按原固定资源重建。编译器版本参与内容摘要与实例版本判断。

`flow-5` 及更早实例保留原始源码、拼图、实例身份、摘要和引用，只能查看历史，不能复制、执行或回退激活。升级前已保存的服务需要通过服务页重新配置并保存新实例；含固定子服务的父流程应先重新保存叶子服务，再明确选择其新实例。不会静默升级旧引用。

2026-09-21 已通过 JSON 仓储恢复断言验证新快照摘要稳定、嵌套路由资源收集、旧协议只读和重新保存。正式 Electron 页面保存 foreach/switch 服务后，隔离 PostgreSQL 停库重启并加载原固定实例，再次真实执行成功；主动取消和应用退出终态跨重启保留。详见[控制流归档记录](archive/2026-09-21/control-flow-expansion-plan.md)。

知识库元数据通过现有文档存储的 `knowledge_bases`、`knowledge_revisions`、`knowledge_versions` 和 `knowledge_files` 集合保存，无新增数据库连接。任务记录的 `knowledgeBindings` 与 `evidence` 保存固定修订和候选/选用证据；旧任务记录缺省为空。原件与知识库历史没有自动物理回收。2026-09-21 已验证文档/服务/任务证据跨本地 PostgreSQL 停库重启恢复，操作见[知识库手册](knowledge.md)。
