# Agent Platform

面向业务系统的桌面 Agent 服务平台。服务中心组合一个或多个业务包与一个或多个配置，由实例组织完整业务入口和流程，通过稳定服务入口提供调用。

## 新需求与当前实现状态

2026-09-17 已更新为[服务拼图需求 v0.5](docs/product-requirements.md)：服务配置页拼装通用块和业务包，逐节点配置后生成完整实例供任务调用；支持类型约束端口、条件与循环，并允许无需模型环境及预算的纯通用块实例。新设计见[架构 v0.3](docs/architecture-design.md)。

**I6、I7 已各完成 7/7 张。** 后端已支持单文件块、端口与逐节点配置预检，以及顺序／条件／循环拼图编译、累计预算、取消、完整实例保存、版本回退和任务调用。API 协议见 [拼图配置说明](examples/flows/README.md)，逐卡证据见 [I7 交接](docs/tasks/i7.md)。

**I8 已完成 8/9 张，查重拼图与调用脚本已迁移。** 桌面已支持模块库、契约选择、顺序/条件/循环拼图、包节点独立配置、草稿、实例保存/历史/回退和任务节点展示。新版服务保存协议为 `{name, flow}`，无需 instance.json。标准模板已迁移，操作见 [模板说明](samples/template/README.md)。新版 M1 已通过，[验收记录](docs/delivery/i8-platform.md)；I8-T09/M2 因缺少真实模型环境阻塞，[准备与解除条件](docs/delivery/i8-similarity.md)。

I7 定向验证：`.venv/bin/python checks/flow_execution.py`、`checks/flow_branches.py`、`checks/flow_loops.py`、`checks/flow_control.py`、`checks/flow_snapshots.py`、`checks/flow_versions.py`、`checks/flow_runs.py`（后六项也使用 `.venv/bin/python` 执行）。仅使用确定性块、合成模型和本地 HTTP 协议替身，不安装依赖或构建。

## 快速启动

以下命令在项目根目录 `/home/nemo/agent-platform` 执行。当前工作区已有 Python `.venv` 和桌面依赖，无需重新安装。

### 方式一：启动桌面应用

```bash
cd /home/nemo/agent-platform
env -u ELECTRON_RUN_AS_NODE npm --prefix desktop start
```

需要可用的图形桌面会话（Linux/WSL 需 X11 或 WSLg）。Electron 会自动启动 Python 后端并分配端口，**无需另外启动后端**。窗口显示“后端已就绪”及实际地址后，就可以配置环境和服务。关闭窗口会停止后端和本地模型传输。

### 方式二：只启动后端 API

```bash
cd /home/nemo/agent-platform
.venv/bin/python -m agent_platform --host 127.0.0.1 --port 8000
```

- 健康检查：浏览器打开 `http://127.0.0.1:8000/api/v1/health`，应返回 `{"status":"ready"}`。
- API 调试页面：`http://127.0.0.1:8000/docs`。
- 此方式不打开桌面窗口，适用于 HTTP 调用和下方命令行样例；终端按 Ctrl+C 停止。
- 如果 8000 被占用，可改为 `--port 8001`，调用脚本同时设置 `--platform-url http://127.0.0.1:8001`。

两种启动方式任选其一；分别启动会产生独立会话。环境、凭据、服务版本、任务及报告目前仅存内存，退出后清空，重启须重新配置。新克隆且没有依赖的环境，先准备 Python 3.12+、uv、Node.js/npm，再自行执行 `uv sync --frozen` 和 `npm --prefix desktop ci`；不需要 PostgreSQL 或本地 Ollama。

## 配置远程模型 API（OpenAI 兼容格式）

支持远程 Chat Completions，不要求在本机部署模型。准备服务商的 **API Base URL、模型名和 API Key**。这是 Chat Completions 接口，当前不使用 Responses API。

### 桌面配置

在“环境配置”中填写环境名称；连接设置只需要填写 **Base URL 和凭据（API Key）**，点击“获取模型”，再从返回的下拉列表选择模型，最后保存环境。不再手写连接 JSON、connectionId 或模型名称。

Base URL 使用服务商提供的 API 根路径，不要填写完整 `/chat/completions` 地址。新建连接默认使用 OpenAI 兼容协议；DeepSeek 地址 `https://api.deepseek.com` 自动使用 `max_tokens`，其他 OpenAI 兼容地址默认使用 `max_completion_tokens`。本地 Ollama 的标准端口 `11434` 自动识别为 Ollama；已有连接加载时保留原协议及参数。特殊协议参数、API 类型连接仍可通过后端环境 API 配置，桌面保存会保留已有其他连接。

凭据单独填写，保存后清空密码框，之后留空表示保留已存凭据。修改 Base URL 会移除旧地址的凭据引用，需重新填写凭据；修改地址或凭据会清空模型选择，须重新获取模型。已有环境直接显示当前保存的模型；如有多个模型连接，可切换连接分别编辑。

### DeepSeek 与模型连接工具

1. Base URL 填 `https://api.deepseek.com`，凭据填 DeepSeek API Key。
2. 点击“获取模型”，从列表选择可用模型。列表为空或请求失败时显示提示，模型不可手动输入。
3. 可点击“测试连接”，实际发送一次小型 JSON 请求，显示耗时及 token 用量。测试输出上限为 256，可能产生模型费用；成功仅代表此请求可用。
4. 点击“保存环境”。服务配置中使用该环境时，预算仍须明确设置 `strictTokenLimit: false`。

获取模型使用 OpenAI 兼容 `GET /models` 或 Ollama `GET /api/tags`；测试和获取列表均使用当前未保存表单，且不创建业务任务。模型选择直接写入待保存配置，无需另外回填。连接标识、JSON 模式、超时时间及输出参数由页面管理。

DeepSeek 依据：[官方接入说明](https://api-docs.deepseek.com/)、[JSON 输出说明](https://api-docs.deepseek.com/guides/json_mode/)。可用模型以实际获取的列表为准。

定向验证（均使用本地协议替身）：`.venv/bin/python checks/connection_tools.py`；真实页面验证：`env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/connection-tools.cjs`。

### 命令行跑通查重

先按“方式二”启动后端，在另一个终端进入项目根目录。下面的 Bash 命令从隐藏输入读取 Key，不写入命令历史：

```bash
read -rsp 'API Key: ' MODEL_API_KEY
export MODEL_API_KEY
printf '\n'

.venv/bin/python samples/invoke_similarity.py \
  --platform-url http://127.0.0.1:8000 \
  --adapter openai-chat \
  --model-url https://api.openai.com/v1 \
  --model YOUR_MODEL_NAME \
  --credential-env MODEL_API_KEY \
  --non-strict \
  --input samples/assignment-similarity/examples/input.json \
  --output /tmp/similarity-report.json

unset MODEL_API_KEY
```

替换模型名和服务商地址后运行。脚本自动创建环境、加载包与单文件块、解析查重拼图并保存服务、提交输入、轮询并导出结果；后端与脚本必须共享本地文件系统。第三方兼容服务可追加 `--output-token-parameter max_tokens` 或 `--no-json-mode`。`unset` 只清除当前终端变量，平台内存中的凭据在后端退出时清空。

约 1500 字的 1 对 6 验收使用 `--input samples/assignment-similarity/examples/acceptance-1v6.json`。真实 API 调用可能产生服务商费用；成功结果包含 quantitative、qualitative、实际适配器、模式及 usage。没有 Key 时可先运行 `.venv/bin/python checks/similarity_onboarding.py` 验证本地协议替身链路，该结果不算真实模型验收。

若仍需 Ollama，显式使用 `--adapter ollama-chat --model-url http://127.0.0.1:11434 --model 已安装的模型名 --non-strict`。旧环境未填写 modelAdapter 时保持 Ollama 行为；新桌面配置和查重脚本默认引导使用 OpenAI 兼容 API。

## 项目状态

**I1 工程与协议基础已完成（13/13）**：Python 后端、Electron 桌面入口、严格契约、统一错误、健康请求 IPC、父子进程启动/退出、包与实例声明、内存内容快照及最小 LangGraph 顺序执行器。各卡真实验证记录见 [I1 交接](docs/tasks/i1.md)。

技术栈为 **FastAPI + Pydantic + LangGraph + PostgreSQL**，桌面为 **Electron + 原生 HTML/CSS/JavaScript**。本次在 Linux 源码环境验收；锁定版本包括 Python 3.12.3 环境下的 FastAPI 0.141.1、Pydantic 2.13.5、Uvicorn 0.53.0、LangGraph 1.2.11，以及 Electron 44.4.1。

**I2 配置与版本管理已完成（12/12）**：内存凭据与环境接口、环境配置页、包与通用块加载、多包配置校验、完整实例快照、版本分配、稳定服务入口、服务配置页及会话历史回退。各卡验证见 [I2 交接](docs/tasks/i2.md)。

**I3 任务与能力执行已完成（13/13）**：运行仓储、环境占用、异步提交与单任务 worker、统一策略检查入口、块/API/Ollama 模型适配器、业务包调用、查询接口与桌面任务面板。逐卡证据见 [I3 交接](docs/tasks/i3.md)，操作与 API 样例见 [执行样例](examples/execution/README.md)。

**I4 预算与终止行为已完成（12/12）**：局部/全局 loop 和 token 账本、严格与非严格策略、预算表单、排队/运行取消、错误优先级、取消按钮及在途退出清理。M1 合成平台闭环通过，见 [演示记录](docs/delivery/i4-platform.md) 和 [I4 交接](docs/tasks/i4.md)。

验收使用合成数据、本地 HTTP 模型协议替身及真实 Electron 页面，尚未验收真实模型。OpenAI 兼容 API 与 Ollama 均不声明严格总 token 保证，严格模式在发送前报错；使用时需明确选择非严格模式，详见 [模型协议能力](docs/protocols/model.md)。I5 已实现查重契约、清洗计分、语义包、完整图、标准模板与接入说明，I5-T08 因缺少可用模型环境阻塞，M2 未完成，见 [I5 交付记录](docs/delivery/i5-similarity.md)；PostgreSQL 仅为后续选型，当前未启用持久化。

- [产品需求文档](docs/product-requirements.md)：已确认范围、行为与验收标准。
- [架构设计文档](docs/architecture-design.md)：运行结构、包与实例协议、版本快照、任务状态机及预算。
- [迭代开发文档](docs/iteration-plan.md)：开发依赖、58 张单目标任务卡、轻量验收与交接记录；任务卡位于 `docs/tasks/`。
- [项目协作约定](AGENT.md)：开发边界与工作约束。

## 查重产品接入

见 [samples 操作说明](samples/README.md)。无需真实模型可执行 `.venv/bin/python checks/similarity_onboarding.py`，从干净后端进程验证加载、配置、双报告与退出。该命令使用本地 HTTP 协议替身，不代替 M2 真实验收。用户 artifact 可通过 `.venv/bin/python checks/similarity_scoring.py --artifact-dir artifact` 在本地测验。

## 运行补充

桌面和独立后端的启动命令见前文 [快速启动](#快速启动)。桌面刷新页面不重启后端，父进程意外消失时通过控制管道 EOF 清理子进程。`AGENT_PLATFORM_PYTHON` 可指定其他兼容解释器，默认使用项目 `.venv/bin/python`。

当前在 Linux 源码环境验证，尚无跨平台安装包或构建发布产物。父子进程控制协议见 [控制协议](examples/control/README.md)。

### WSL 中文显示为方框

页面使用 UTF-8；中文显示为方框时，先用 `fc-list ':lang=zh'` 检查系统是否识别中文字体。CSS 字体回退列表不能替代实际字体文件。

若 Windows 字体目录 `/mnt/c/Windows/Fonts` 已存在，可在当前用户的 `~/.config/fontconfig/conf.d/90-windows-fonts.conf` 中添加以下配置，然后执行 `fc-cache /mnt/c/Windows/Fonts` 并完全退出、重新启动桌面应用。此方式只引用本机现有字体，不将 Windows 字体复制进仓库。

```xml
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>/mnt/c/Windows/Fonts</dir>
</fontconfig>
```

本次修复已通过真实 Electron 窗口截图确认：“后端已就绪”和“检查健康状态”均正常显示。

## 局部验证与样例

在根目录执行对应命令，无需模型端点、密钥或数据库：

| 范围 | 验证命令 |
| --- | --- |
| 严格嵌套模型与 Schema | `.venv/bin/python checks/contracts.py` |
| 错误路径与认证信息隔离 | `.venv/bin/python checks/errors.py` |
| HTTP 就绪与端口释放 | `.venv/bin/python checks/health.py` |
| 控制消息 | `.venv/bin/python checks/control.py` |
| 包与实例声明 | `.venv/bin/python checks/packages.py`、`.venv/bin/python checks/instances.py` |
| 源码、延迟导入与 Prompt 快照隔离 | `.venv/bin/python checks/snapshots.py` |
| 真实 LangGraph 两节点与状态隔离 | `.venv/bin/python checks/graphs.py` |
| 真实桌面窗口 | `env -u ELECTRON_RUN_AS_NODE npm --prefix desktop run check:window` |
| 启动与错误展示 | `env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/backend.cjs` |
| preload 与页面刷新 | `env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/ipc.cjs` |
| 窗口退出和父进程消失 | `node desktop/checks/lifecycle.cjs` |
| 端口占用与启动期间退出 | `node desktop/checks/startup.cjs` |

桌面检查需要可用的图形会话。桌面验收使用现有 X11 显示环境；I3 模型适配器另用本地 HTTP 替身验证，未使用真实模型。

- [声明样例](examples/declarations/README.md) 仅用于契约校验，符号引用不代表完整业务包已实现。
- `.venv/bin/python examples/workflow/two_nodes.py` 可直接运行确定性两节点图。
- `.venv/bin/python scripts/export_contracts.py` 从 Python 权威模型更新桌面使用的 JSON Schema。
- 快照 API：`capture(directory)` → `snapshot.load('entry:invoke')`；自有模块使用相对导入，资源通过 `snapshot.read_resource('prompt.txt')` 获取。内容只存内存，显式 `close()` 应在所有使用者结束后调用；受信任代码加载不是沙箱。

## 配置与版本操作

通过侧栏切换环境、服务和任务页面。先保存模型环境（纯块流程无需环境），再在服务页面：

1. 加载单文件 `.py` 块、业务包目录或 Python 契约 symbol。可用 `samples/template/blocks/text.py` 开始。
2. 选择输入输出契约，在模块库或容器内插入节点。用来源/目标下拉接线，前序输出可引用，结构不兼容须显式转换块。
3. 包节点点击“配置”，按 Schema 填参数、预算并选择环境连接；同包不同节点独立。条件与循环按容器编辑分支出口、次数和携带值。
4. 输入未完成时可“保存草稿”；合法内容“校验并保存实例版本”后立即生效。输入样例在保存时校验。
5. 历史可查看完整只读拼图、复制为编辑草稿或回退原实例。任务页选择稳定服务，填入样例、提交、查询节点/循环路径、用量和结果或取消。

以上只保存本次会话。刷新页面保留后端草稿、实例及目录，未保存输入仍会丢失。服务更新或回退不改变已提交任务的固定实例与环境。

定向真实页面命令：`env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/flow-editor.cjs`；按对应卡选择 `node-configuration.cjs`、`flow-controls.cjs`、`flow-history.cjs`、`flow-tasks.cjs`、`template-page.cjs`。模型检查使用本地协议替身，逐卡证据见 [I8](docs/tasks/i8.md)。

## 现有交付与保留规则（新版范围见需求）

- 平台：桌面服务／环境配置页、受信任本地包加载、Python 通用块、版本历史与回退、异步任务和报告查询。
- 业务产品：标准包模板与实例模板、最小查重实例及语义分析包，位于 `samples/`；完成约 1500 字文本的 1 对 6 比较。
- 定量相似度由实例中的确定性代码按重复段落计算；定性报告由模型生成，教师自行判断，不验证模型准确率。

每次更新完整保留入口脚本、流程、包内容和配置快照。旧实例退役后不能直接调用，需在中心选择历史版本回退；稳定入口保持不变。所有历史、配置、任务和报告当前仅在内存，退出桌面程序即清空，数据库版本才支持跨重启历史。

排队、运行或取消等待任务占用的环境不可修改。失败保留任务终态并清理运行上下文。主动取消等待当前模型传输结束；等待期间超时/断连优先报错。桌面退出立即中止在途传输。

I4 已装配包调用 loop 与可配置 token 策略，局部和全局同时约束；失败尝试仍计 loop。预算表单保存生成新版本；不自动重试、不实现去重键。

## 目录

```text
agent-platform/
├── AGENT.md
├── readme.md
├── pyproject.toml / uv.lock
├── docs/                       # 需求、架构、迭代索引与逐卡证据
├── desktop/                    # Electron 主进程、preload、本地页面与定向检查
├── src/agent_platform/          # 后端入口、契约、快照加载器、顺序图运行时
├── examples/                   # 控制消息、声明样例、两节点图
├── checks/                     # 轻量定向断言
├── scripts/                    # 契约导出与任务交接记录工具
└── samples/                    # 标准模板、查重实例与语义包、接入脚本
```

权限、数据库持久化与直连、复杂业务规则、性能优化等后置。

## 开发约束

开始实现前阅读协作约定及三份设计文档。依赖安装、权限修改、重型测试、构建和发布遵循协作约定；文档完成不代表已授权执行这些操作。
