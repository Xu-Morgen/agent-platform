# Agent Platform

通过桌面服务页组合 Python 通用块、业务包和独立契约，保存为可调用的服务实例。支持顺序、条件、有限循环、版本回退、任务查询和取消。桌面自动管理本地 PostgreSQL，配置和历史跨重启保留；模型输入输出受严格契约约束，流程由配置者定义，分支与循环条件由脚本块判断。产品路径见 [分步计划](docs/agent-platform-roadmap.md)。

## 启动

在仓库根目录，使用已有依赖：

```bash
env -u ELECTRON_RUN_AS_NODE npm --prefix desktop start
```

Electron 自动启动后端；页面顶部显示实际地址。需要图形会话，关闭窗口会停止后端和本地模型传输，并正常关闭本应用数据库、保留数据。也可单独启动 API：

```bash
.venv/bin/python -m agent_platform --host 127.0.0.1 --port 8000
```

健康检查为 `http://127.0.0.1:8000/api/v1/health`，接口文档为 `http://127.0.0.1:8000/docs`。桌面与独立启动的后端默认使用同一数据目录，不能同时启动；独立开发可用 `--data-dir` 指定其他目录。`AGENT_PLATFORM_PYTHON` 可指定桌面使用的 Python，默认使用项目 `.venv/bin/python`。

新环境需要 Python 3.12+、uv、Node.js/npm 和 PostgreSQL 运行程序；执行 `uv sync --frozen` 与 `npm --prefix desktop ci` 准备依赖。Ubuntu 24.04 可运行 `.venv/bin/python scripts/install_local_postgres.py` 准备用户级数据库程序。当前工作环境已安装并通过真实数据库联调，无需手填数据库连接或主密钥。详见 [持久化说明](docs/persistence.md)。

本机数据目录为 `/home/nemo/.config/Agent Platform/storage/`，其中 `postgresql/` 保存数据库文件，`secrets.json` 保存本机密钥；页面显示实际路径。不要删除密钥文件。

## 使用

1. 普通计算块服务可直接开始。API 块先在环境页保存 API Base URL、可选凭据和超时。需要模型时，填写模型 Base URL 和凭据，获取并选择模型后保存；“测试连接”会发送一次真实小型请求。
2. 在服务页左侧「加载本地资源」中加载单文件通用块、业务包目录或独立契约。在「开始」选择服务输入类型，从模块库搜索添加节点，或点击流程中的「＋」插入到指定位置。展开节点，按「从哪里取值 → 传给哪里」配置数据映射；在「返回结果」选择输出类型和返回来源。需要外部信息时，可配置 [API 通用块](samples/blocks/README.md)。结构转换使用通用块。
3. 包节点分别配置参数、模型连接、预算和单次输出上限。模型统一使用 OpenAI 兼容接口，token 按实际用量累计。普通计算块无需环境；API 块单独选择 API 连接并填写请求路径，无需模型预算。
4. 可先保存草稿；“校验并保存版本”成功后立即生效。
5. 任务页选择服务，在输入区填写 JSON 或填入服务样例后提交。任务详情显示实际输入、状态、用量、步骤和最终结果，执行期间可取消；历史列表支持筛选、翻页和重新打开任务。服务历史支持查看、复制草稿及回退。

完整操作和可复制样例见 [三类资源指导手册](docs/resource-guide.md)、[样例入口](samples/README.md)。模型连接选项见 [模型协议](docs/protocols/model.md)。

2026-09-18 起业务包仅维护输入输出契约、可选参数和 Prompt；平台统一执行模型调用与严格校验。数据转换使用通用块。旧包迁移见 [包开发说明](samples/packages/README.md)。

## 当前边界

- 桌面固定使用本地 PostgreSQL，启动失败不会降级为内存；仅开发命令 `--memory` 显式启用临时存储。已验收 Ubuntu 24.04，未交付 Windows 生命周期或跨平台安装包。
- 本地 Python 资源是受信任代码，后端与加载脚本须共享文件系统；尚无第三方代码沙箱。
- 单 worker 串行消费任务，不自动重试、不去重、不自动续跑；重启恢复记录，将未完成任务标为中断。LangGraph 检查点暂未启用。任务页支持筛选与分页查看历史。
- 已提交任务固定实例内容和实际环境；版本更新不影响在途任务，占用中的环境不可修改。
- 主动取消等待当前模型传输结束；等待中超时或断连记失败。关闭应用立即停止本地传输。
- 当前 samples 每类只提供最小与最完整两套开发模板，API 能力包含在通用块 complete.py 中；原查重样例已按要求删除。

## 后续开发与目录

从 [文档导航](docs/README.md) 查看当前需求、架构和使用手册。[Agent 平台分步计划](docs/agent-platform-roadmap.md)定义本轮定位、已实现内容和后续步骤；[产品细化计划](docs/product-refinement.md)保留其他体验优化项；[三类资源优化计划](docs/resource-plan.md)分别定义通用块、业务包和契约的改进。已完成交付、清理记录和旧方案见 [历史归档](docs/archive/README.md)。

| 路径 | 用途 |
| --- | --- |
| `src/agent_platform/` | 契约、资源目录、拼图编译、任务执行和 HTTP API |
| `desktop/` | Electron 主进程、IPC 和页面 |
| `samples/blocks/` | 单文件通用块最小/完整实现及输入配置说明 |
| `samples/packages/` | 业务包最小/完整实现、清单、节点配置与平台标准入口说明 |
| `samples/contracts/` | 独立契约最小/完整实现、字段及校验钩子说明 |
| `samples/USAGE.md` | 三类资源加载、服务接线、保存与调用示例 |
| `scripts/export_contracts.py` | 从权威模型生成桌面控制协议 Schema |
| `docs/` | 当前需求、架构、未完成计划、手册和协议；历史资料集中在 `docs/archive/` |
| `artifact/` | 用户保留资料，本轮未改动 |

旧测试脚本、测试数据和旧实例执行入口已移除。2026-09-17 按新要求清空并重建 samples，原查重代码、流程配方和辅助脚本不再保留。历史交接中的旧命令仅作记录，当前入口以本页和手册为准。开发约定见 [AGENT.md](AGENT.md)。
