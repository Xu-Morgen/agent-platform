# 标准包与实例模板

`packages/example/` 是单次模型交互包；`instance/` 是独立的两步 LangGraph 实例。
默认两个绑定 `first`、`second` 复用同版本包，各有独立配置。要组合两个不同包，复制包目录并修改各自 `package.json.packageId`，再修改实例 `packageBindings` 的包标识。实例自己的标识是 `instance.json.definitionId`。

- 配置分别位于 `packages.first`、`packages.second`，可独立修改 instruction、maxOutputTokens 和局部预算。
- 两次包调用需要全局 loopLimit 至少为 2；普通图节点不消耗 loop。
- 环境占位符须替换为平台创建的 environmentId，连接 ID 为 model。
- 默认严格模式；当前 Ollama 适配器需明确改为非严格模式才能调用，不会自动降级。
- 业务契约只编辑 `instance/contracts.py`，执行 `.venv/bin/python samples/template/sync_contracts.py` 后分发包。`--check` 验证副本同步，两个目录可独立快照加载。
- `.venv/bin/python checks/template_copy.py` 在临时目录复制并重命名两包与实例，使用本地 HTTP 替身验证两配置和两轮调用；不是实际模型验收。

包不包含地址、密钥或完整业务流程。启动与调用步骤见 [samples 接入说明](../README.md)。
