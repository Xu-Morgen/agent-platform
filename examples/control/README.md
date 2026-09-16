# 控制协议 v1

消息为 UTF-8 JSON Lines，每条消息以换行结束；必须显式包含整数 `protocolVersion: 1`。模型权威来源为 `src/agent_platform/contracts/control.py`。

- 父→子：子进程 stdin 是专用控制输入，接收 `shutdown`，不可混入用户交互输入。
- 子→父：子进程 fd 3 是专用控制输出，发送一次 `ready` 或 `startupError`。地址是后端实际绑定的 HTTP 地址；父进程仍须完成健康检查才开放操作。
- stdout/stderr 仅输出普通日志，不用于解析控制消息。
- `shutdown` 的原因固定为 `APPLICATION_EXIT`；stdin EOF 与主动 shutdown 具有相同的退出语义。未知类型、错误版本与畸形消息为协议错误，不得当作 ready。
- 此卡只定义协议。启动、EOF 监听及有界退出分别由 I1-T07、I1-T09 实现。

运行 `.venv/bin/python checks/control.py` 验证样例。
