# Agent Platform

通过桌面服务页组合 Python 通用块、业务包和独立契约，保存为可调用的服务实例。支持顺序、条件、有限循环、版本回退、任务查询和取消。用户已于 2026-09-17 确认当前最小产品验证完成；接下来在此基线上细化产品。

## 启动

在仓库根目录，使用已有依赖：

```bash
env -u ELECTRON_RUN_AS_NODE npm --prefix desktop start
```

Electron 自动启动后端；页面顶部显示实际地址。需要图形会话，关闭窗口会停止后端和本地模型传输。也可单独启动 API：

```bash
.venv/bin/python -m agent_platform --host 127.0.0.1 --port 8000
```

健康检查为 `http://127.0.0.1:8000/api/v1/health`，接口文档为 `http://127.0.0.1:8000/docs`。桌面与单独启动的后端是两个独立会话。`AGENT_PLATFORM_PYTHON` 可指定桌面使用的 Python，默认使用项目 `.venv/bin/python`。

新环境需要 Python 3.12+、uv、Node.js/npm；由使用者执行 `uv sync --frozen` 与 `npm --prefix desktop ci` 准备依赖。当前不需要 PostgreSQL 或本地模型部署。

## 使用

1. 普通计算块服务可直接开始。API 块先在环境页保存 API Base URL、可选凭据和超时。需要模型时，填写模型 Base URL 和凭据，获取并选择模型后保存；“测试连接”会发送一次真实小型请求。
2. 在服务页加载单文件通用块、业务包目录或独立契约，选择服务输入输出类型并插入节点。需要外部信息时，可配置 [API 通用块](samples/blocks/README.md)。显式接线；结构转换使用通用块。
3. 包节点分别配置参数、模型连接、预算和单次输出上限。模型统一使用 OpenAI 兼容接口，token 按实际用量累计。普通计算块无需环境；API 块单独选择 API 连接并填写请求路径，无需模型预算。
4. 可先保存草稿；“校验并保存实例版本”成功后立即生效。
5. 任务页选择稳定服务，填写业务输入并提交，查看节点结果、用量或取消。服务历史支持查看、复制草稿及回退。

完整操作和可复制样例见 [三类资源指导手册](docs/resource-guide.md)、[样例入口](samples/README.md)。模型连接选项见 [模型协议](docs/protocols/model.md)。

2026-09-18 起业务包仅维护输入输出契约、可选参数和 Prompt；平台统一执行模型调用与严格校验。数据转换使用通用块。旧包迁移见 [包开发说明](samples/packages/README.md)。

## 当前边界

- 配置、凭据、草稿、版本、任务与报告仅存内存，退出后清空；文件导出的报告不会自动恢复到平台。
- 本地 Python 资源是受信任代码，后端与加载脚本须共享文件系统；尚无第三方代码沙箱。
- 单 worker 串行消费任务，不自动重试、不去重、不提供跨重启恢复。
- 已提交任务固定实例内容和实际环境；版本更新不影响在途任务，占用中的环境不可修改。
- 主动取消等待当前模型传输结束；等待中超时或断连记失败。关闭应用立即停止本地传输。
- 当前 samples 每类只提供最小与最完整两套开发模板，API 能力包含在通用块 complete.py 中；原查重样例已按要求删除。

## 后续开发与目录

从 [文档导航](docs/README.md) 查看当前需求、架构和使用手册。[产品细化计划](docs/product-refinement.md)规定优先级和验收目标；[三类资源优化计划](docs/resource-plan.md)分别定义通用块、业务包和契约的改进。已完成交付、清理记录和旧方案见 [历史归档](docs/archive/README.md)。

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
