# 桌面父子进程控制协议 v1

权威模型为 `src/agent_platform/contracts/control.py`。消息采用 UTF-8 JSON Lines，每条以换行结束，显式包含整数 `protocolVersion: 1`。

- 父→子：后端 stdin 为专用控制输入，接收 shutdown；不能混入用户交互输入。
- 子→父：后端 fd 3 为专用控制输出，发送一次 ready 或 startupError。ready 携带实际 HTTP 地址，父进程完成健康检查后开放操作。
- stdout/stderr 仅输出日志，不解析为控制消息。
- shutdown 原因为 APPLICATION_EXIT；stdin EOF 也触发退出。退出立即停止本地传输并清理后端进程。
- 未知消息、错误版本及畸形 JSON 不能当作 ready。

`desktop/main/backend.cjs` 管理后端生命周期，`server.py` 和 `__main__.py` 处理 Python 启动/退出；独立 API 模式不要求父进程控制通道。`scripts/export_contracts.py` 从权威模型生成桌面使用的 Schema。

父子进程启动协议独立于服务执行协议；FlowDraft、NodeInput 与旧实例边界见 [架构说明](../architecture-design.md#13-flow-6-入口与历史边界)。
