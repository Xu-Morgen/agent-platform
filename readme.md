# Agent Platform

面向业务系统的桌面 Agent 服务平台。服务中心组合一个或多个业务包与一个或多个配置，由实例组织完整业务入口和流程，通过稳定服务入口提供调用。

## 项目状态

**I1 工程与协议基础已完成（13/13）**：Python 后端、Electron 桌面入口、严格契约、统一错误、健康请求 IPC、父子进程启动/退出、包与实例声明、内存内容快照及最小 LangGraph 顺序执行器。各卡真实验证记录见 [I1 交接](docs/tasks/i1.md)。

技术栈为 **FastAPI + Pydantic + LangGraph + PostgreSQL**，桌面为 **Electron + 原生 HTML/CSS/JavaScript**。本次在 Linux 源码环境验收；锁定版本包括 Python 3.12.3 环境下的 FastAPI 0.141.1、Pydantic 2.13.5、Uvicorn 0.53.0、LangGraph 1.2.11，以及 Electron 44.4.1。

**I2 配置与版本管理已完成（12/12）**：内存凭据与环境接口、环境配置页、包与通用块加载、多包配置校验、完整实例快照、版本分配、稳定服务入口、服务配置页及会话历史回退。各卡验证见 [I2 交接](docs/tasks/i2.md)。

**I3 任务与能力执行已完成（13/13）**：运行仓储、环境占用、异步提交与单任务 worker、统一策略检查入口、块/API/Ollama 模型适配器、业务包调用、查询接口与桌面任务面板。逐卡证据见 [I3 交接](docs/tasks/i3.md)，操作与 API 样例见 [执行样例](examples/execution/README.md)。

**I4 预算与终止行为已完成（12/12）**：局部/全局 loop 和 token 账本、严格与非严格策略、预算表单、排队/运行取消、错误优先级、取消按钮及在途退出清理。M1 合成平台闭环通过，见 [演示记录](docs/delivery/i4-platform.md) 和 [I4 交接](docs/tasks/i4.md)。

验收使用合成数据、本地 HTTP 模型协议替身及真实 Electron 页面，尚未验收真实模型。Ollama 不声明严格总 token 保证，严格模式在发送前报错；使用该适配器需明确选择非严格模式，详见 [模型协议能力](docs/protocols/model.md)。查重产品留 I5；PostgreSQL 仅为后续选型，当前未启用持久化。

- [产品需求文档](docs/product-requirements.md)：已确认范围、行为与验收标准。
- [架构设计文档](docs/architecture-design.md)：运行结构、包与实例协议、版本快照、任务状态机及预算。
- [迭代开发文档](docs/iteration-plan.md)：开发依赖、58 张单目标任务卡、轻量验收与交接记录；任务卡位于 `docs/tasks/`。
- [项目协作约定](AGENT.md)：开发边界与工作约束。

## 本地运行

已安装本项目依赖的工作区，在根目录运行：

```bash
# 单独启动后端，默认仅监听本机；不与桌面共享进程
.venv/bin/python -m agent_platform --port 8000

# 启动桌面，由主进程创建唯一后端并选择空闲端口
# 清除 IDE 可能注入的 Electron Node 模式
env -u ELECTRON_RUN_AS_NODE npm --prefix desktop start
```

桌面显示实际地址，健康检查成功后启用“检查健康状态”按钮。页面刷新不重启后端，关闭最后一个窗口会关闭后端；父进程意外消失也触发控制管道 EOF 清理。`AGENT_PLATFORM_PYTHON` 可指定其他兼容解释器；默认使用项目 `.venv/bin/python`。独立后端支持 `--host` 配置 IPv4 监听地址。

健康接口：`GET http://127.0.0.1:8000/api/v1/health`，响应 `{"status":"ready"}`。控制管道规范及三类消息见 [控制协议](examples/control/README.md)。

新工作区需先按协作约定取得安装授权，再用 `uv sync --frozen` 和 `npm --prefix desktop ci` 安装锁定依赖。当前未提供跨平台安装包或构建发布产物。

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

1. 环境配置区填写名称和连接 JSON；凭据在独立密码框输入，保存后只返回引用。模型连接须指定 `model`，API 连接使用 `kind: "api"`。
2. 服务配置区先选择“通用块”加载 `examples/configuration/block`，再选择“业务包”依次加载 `examples/configuration/package` 和 `examples/configuration/second`。
3. 选择“实例定义”加载 `examples/configuration/instance`；页面展示两包两配置 JSON、输入输出及配置 Schema，全局默认预算为 loop 4、token 200，可编辑。
4. 填写服务名称，校验并保存得到稳定 serviceId 和版本 1.0；修改配置再保存得到新实例与 1.1。
5. 在本次会话历史中选回 1.0，稳定服务指向原实例；不会恢复旧环境地址或生成新版本。退出重启后环境、服务、凭据和历史清空。

以上为配置能力样例，不调用模型。目录可填写绝对路径；相对路径按后端工作目录解析。完整样例及 API 说明见 [配置样例](examples/configuration/README.md)。

定向验证：`.venv/bin/python checks/registry_api.py` 验证加载与保存，`.venv/bin/python checks/activation.py` 验证回退边界；真实页面检查使用 `env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/environments.cjs` 与 `desktop/checks/services.cjs`（后者也需以 Electron 启动）。其余单卡命令见 I2 交接。

## 核心概念

| 概念 | 定义 |
| --- | --- |
| 业务包 | 类似可复用依赖，封装 LLM 交互前后的输入输出、Prompt 与必要处理 |
| 服务配置 | 包参数、能力绑定、环境引用及预算等配置单元 |
| 服务实例 | 一个或多个固定版本包和配置，加上完整入口脚本、业务流程与服务契约 |
| 服务 | 拥有稳定标识，指向服务中心当前选定的实例版本 |
| 环境 | 模型/API 连接和认证等共享设置，变更不改变实例版本 |

```text
加载业务包和实例流程
    → 配置环境，组合包及配置
    → 校验保存完整实例快照，稳定入口切换到新版本
    → 提交任务，固定实例与环境，执行并校验结果
```

当前平台已提供配置、契约校验、模型及通用块调用、任务状态和运行记录；实例组织业务流程，包不承担完整业务编排。平台核心不包含查重业务分支。

## 首期完整目标（后续阶段继续实现）

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
└── samples/                    # 后续 I5 业务产品，尚未实现
```

权限、数据库持久化与直连、复杂业务规则、性能优化等后置。

## 开发约束

开始实现前阅读协作约定及三份设计文档。依赖安装、权限修改、重型测试、构建和发布遵循协作约定；文档完成不代表已授权执行这些操作。
