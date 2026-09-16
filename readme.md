# Agent Platform

面向业务系统的桌面 Agent 服务平台。服务中心组合一个或多个业务包与一个或多个配置，由实例组织完整业务入口和流程，通过稳定服务入口提供调用。

## 项目状态

**I1 工程与协议基础已完成（13/13）**：Python 后端、Electron 桌面入口、严格契约、统一错误、健康请求 IPC、父子进程启动/退出、包与实例声明、内存内容快照及最小 LangGraph 顺序执行器。各卡真实验证记录见 [I1 交接](docs/tasks/i1.md)。

技术栈为 **FastAPI + Pydantic + LangGraph + PostgreSQL**，桌面为 **Electron + 原生 HTML/CSS/JavaScript**。本次在 Linux 源码环境验收；锁定版本包括 Python 3.12.3 环境下的 FastAPI 0.141.1、Pydantic 2.13.5、Uvicorn 0.53.0、LangGraph 1.2.11，以及 Electron 44.4.1。

I2—I5 尚未实现：配置页面、服务版本管理、任务 API、真实模型调用、预算执行与查重产品仍待后续任务。PostgreSQL 仅为后续选型，当前未启用持久化。

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

桌面检查需要可用的图形会话。当前验收使用现有 X11 显示环境，没有模型替身或真实模型调用。

- [声明样例](examples/declarations/README.md) 仅用于契约校验，符号引用不代表完整业务包已实现。
- `.venv/bin/python examples/workflow/two_nodes.py` 可直接运行确定性两节点图。
- `.venv/bin/python scripts/export_contracts.py` 从 Python 权威模型更新桌面使用的 JSON Schema。
- 快照 API：`capture(directory)` → `snapshot.load('entry:invoke')`；自有模块使用相对导入，资源通过 `snapshot.read_resource('prompt.txt')` 获取。内容只存内存，显式 `close()` 应在所有使用者结束后调用；受信任代码加载不是沙箱。

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

完整平台将提供配置、契约校验、模型及通用块调用、任务状态和运行记录；实例组织业务流程，包不承担完整业务编排。平台核心不包含查重业务分支。

## 首期完整目标（后续阶段继续实现）

- 平台：桌面服务／环境配置页、受信任本地包加载、Python 通用块、版本历史与回退、异步任务和报告查询。
- 业务产品：标准包模板与实例模板、最小查重实例及语义分析包，位于 `samples/`；完成约 1500 字文本的 1 对 6 比较。
- 定量相似度由实例中的确定性代码按重复段落计算；定性报告由模型生成，教师自行判断，不验证模型准确率。

每次更新完整保留入口脚本、流程、包内容和配置快照。旧实例退役后不能直接调用，需在中心选择历史版本回退；稳定入口保持不变。所有历史、配置、任务和报告当前仅在内存，退出桌面程序即清空，数据库版本才支持跨重启历史。

排队、运行或取消等待任务占用的环境不可修改。失败与取消保留任务终态，清理运行上下文并恢复实例就绪；取消等待超时或传输失败优先报错，退出桌面程序立即中止本地传输。

单任务按包调用尝试累计 loop，失败和重试也计数；token 限额是否严格执行可配置，每次状态流转前检查预算。首期不自动重试、不实现去重键。

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
