# I4 平台闭环演示记录

> 历史交接记录：本页记录当时的实现及验证，不是当前使用入口。2026-09-17 用户已确认最小产品验证完成；精简后旧测试命令、数据和入口已移除。当前状态见 [迭代索引](../iteration-plan.md)，操作见 [项目入口](../../readme.md)。

> 本文保留旧基线验收证据。2026-09-17 新服务拼图需求须按 [I8 任务](../tasks/i8.md)重新验收 M1/M2，本文不证明新版已交付。

- 日期：2026-09-17。
- 结论：I4 12/12 完成，M1 平台控制能力通过。
- 环境：现有 Python `.venv`、Electron 图形会话；本地 HTTP 合成 Ollama 协议响应。未安装依赖、未打包、未执行全量测试，未验收真实模型语义或计费。

## 配置、更新、提交、回退和查询

执行 `.venv/bin/python checks/platform_delivery.py`，实际结果：

1. 创建模型环境并保存服务 A（1.0），包输出限额为 10；worker 未启动时提交任务 A，状态 queued。
2. 修改配置为输出限额 20，保存 B（1.1）并提交任务 B；新旧实例 ID 不同。
3. 环境更新返回 409 `ENVIRONMENT_IN_USE`；使用 A 的 expectedInstanceId 提交返回 409，不允许退役实例直调。
4. 回退至 A 后，两个排队任务的实例快照仍分别是 A、B。
5. 启动 worker，本地模型实际收到的输出限额依次为 10、20；查询结果分别为“固定配置 10”“固定配置 20”。两个任务均 completed，每个任务 loop=1、token=5；查询当前服务仍为 A。
6. 任务结束释放环境，更新环境成功。无任务恢复或持久化。

## 桌面与控制行为

以下命令均在本次 I4 实施中实际执行通过，逐卡证据见 [I4 任务卡](../tasks/i4.md)。

| 命令（根目录执行） | 实际结果 |
| --- | --- |
| `env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/budgets.cjs` | 页面改包预算与严格开关生成 1.1；重开表单一致；合成估算输入展示局部/全局及来源；历史按钮回退 A |
| `env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/cancel.cjs` | 点击取消显示等待；放行响应后已取消；超时显示 failed 和 MODEL_TIMEOUT；本地响应的局部/全局 token=5 |
| `env -u ELECTRON_RUN_AS_NODE desktop/node_modules/.bin/electron desktop/checks/inflight-exit.cjs` | 真实关闭窗口，阻塞模型连接中止，后端退出码 0，小于 2 秒；重启查询原运行和排队 ID 均 404 |
| `.venv/bin/python checks/cancel_queued.py` | 排队取消后不执行；事件屏障控制领取竞争；重复取消幂等 |
| `.venv/bin/python checks/cancel_errors.py` | 取消后超时/断连均 failed 且保留取消标记；环境可修改；退役实例未激活 |
| `.venv/bin/python checks/budget_execution.py` | 两节点图无法绕过预算，包括空自带 Boundary；最后一轮可结束；图递归限制独立报错（异常替身） |
| `.venv/bin/python checks/model_package.py` | 本地 HTTP 模型成功、满额成功、超额无结果、严格不支持时零请求 |
| `.venv/bin/python checks/strict_tokens.py` | 严格合成适配器：输入预检、输出收缩、预留核销、失败上界保留 |
| `.venv/bin/python checks/non_strict_tokens.py` | 超额下一流转失败，未知计量明确报错，估算来源保留 |
| `.venv/bin/python checks/api_execution.py`、`.venv/bin/python checks/lms.py` | API→LMS 解包成功；超时、业务及契约错误未转为空成功 |

## 接口与使用边界

- `POST /api/v1/runs/{runId}/cancel` 无请求体，返回 Run。queued 可直接 cancelled；running 先设置 cancelRequested，模型在途时 cancelPhase=waiting_transport。正常响应后 cancelled，超时或断连 failed；终态重复请求不修改结果。
- `GET /api/v1/runs/{runId}` 的 usage.loops 包含 global 与 bindings；usage.tokens 同样分层，包含 inputTokens、outputTokens、totalTokens、knownTokens、reservedTokens、quality、sources。未知总量为 null，不能当作精确 0。
- 预算来自任务固定实例快照；修改表单生成配置版本，不修改排队或运行任务。
- Ollama 当前不支持严格总 token 保证，严格模式发送前返回 TOKEN_ACCOUNTING_UNSUPPORTED；可明确选择非严格模式。缺失 usage 且无法估算时仍失败，不静默降级。
- 严格能力由合成适配器验证，不代表已验证真实供应商的完整 token 保证。预留与实际只核销一次，错误尝试不退还 loop。
- M2 标准模板、查重产品及真实模型 1 对 6 验收属于 I5，尚未完成。PostgreSQL 持久化与跨重启恢复不在本次范围。
