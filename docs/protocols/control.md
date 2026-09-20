# 桌面父子进程控制协议 v1

权威模型为 `src/agent_platform/contracts/control.py`。消息采用 UTF-8 JSON Lines，每条以换行结束，显式包含整数 `protocolVersion: 1`。

- 父→子：后端 stdin 为专用控制输入，接收 shutdown；不能混入用户交互输入。
- 子→父：后端 fd 3 为专用控制输出，发送一次 ready 或 startupError。ready 携带实际 HTTP 地址，父进程完成健康检查后开放操作。
- stdout/stderr 仅输出日志，不解析为控制消息。
- shutdown 原因为 APPLICATION_EXIT；stdin EOF 也触发退出。退出立即停止本地传输并清理后端进程。
- 未知消息、错误版本及畸形 JSON 不能当作 ready。

`desktop/main/backend.cjs` 管理后端生命周期，`server.py` 和 `__main__.py` 处理 Python 启动/退出；独立 API 模式不要求父进程控制通道。`scripts/export_contracts.py` 从权威模型生成桌面使用的 Schema。

服务拼图执行协议独立升级为 flow-5，不改变本页父子进程 protocolVersion=1。if.condition 与 while.condition 均为完整 kind=block 节点，支持 references；NodeInput 与 FlowDraft 的公开 Schema 来自权威 Python 契约和 FastAPI OpenAPI。节点入口封装不是桌面启动消息。旧实例的 compilerVersion 只用于历史读取和执行边界判断。
