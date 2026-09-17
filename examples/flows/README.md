# I6 拼图配置协议

I6 交付结构、资源与预检；图编译及调用在 I7 实施。`control.json` 是包含四类结构的最小协议样例，使用占位资源名，只证明结构校验。
`flow.schema.json` 从 `FlowDraft` 导出；`validation.schema.json` 从统一 `ValidationResult` 导出。不要手写第二份字段定义。

## 可复现的纯块预检

从仓库根目录启动 `.venv/bin/python -m agent_platform` 后，按启动日志地址调用以下 API（前缀 `/api/v1`）：

1. `POST /catalog/load`，请求 `{"kind":"block","path":"examples/flows/blocks/rename.py"}`。
2. `POST /catalog/load`，请求 `{"kind":"block","path":"examples/flows/blocks/condition.py"}`。
3. `GET /catalog` 列出用途、输入输出 Schema 与可复用契约引用；`GET /catalog/{resourceId}` 获取单个资源。
4. `POST /flows/validate`，请求体使用 `valid-draft.json`，响应 `{"valid":true,"issues":[]}`。资源 ID 包含内容摘要；改动示例文件后须使用加载接口返回的新 ID。
5. `POST /drafts`，同样使用 `valid-draft.json`，返回 `draftId` 和 `content`；`GET /drafts/{draftId}` 读取，`PUT /drafts/{draftId}` 更新。
6. `POST /drafts/{draftId}/validate` 预检已保存版本。不完整内容如 `{"content":{"name":"未完成"}}` 也可保存，但预检失败；不会生成 instanceId 或可调用服务。重启后草稿及目录清空。

局部验收命令：`.venv/bin/python checks/flow_drafts.py`。该检查还包含 while 前置条件、循环携带值、非法样例、重启清空及服务隔离。`node desktop/checks/flow-bridge.cjs` 使用替身传输检查全部新 IPC 路由，不代表图形界面验收。

## 模块和契约加载

- 包：`{"kind":"package","path":"examples/execution/model-package"}`；加载不要求环境，不调用业务入口。
- 单文件块：`blocks/rename.py` 做字段转换，`blocks/condition.py` 输出严格 bool，`blocks/lms.py` 要求 `code="10000"` 且 `bizData={"text":"..."}`。失败 code 或错误 bizData 拒绝；不是任意业务契约的通配解包器。
- 独立契约：`{"kind":"contract","path":"examples/flows/blocks/rename.py","symbol":"Output"}`。可复用模块的 inputContract/outputContract，无须另存文件。
- Python 文件是受信任开发代码：加载执行导入与声明，绝不调用注册业务函数。单文件块不支持相对自有代码导入；额外第三方依赖须在装饰器 dependencies 声明且预先安装。

## 节点配置与接线

`POST /flows/validate-node` 接受 `node`、`configuration`、`strictTokenLimit`，返回 `valid`、`issues` 及合法的规范化 `configuration`。参数默认值在规范化响应中显式提供。预算放在 configuration.budget，能力按 capabilityId 绑定环境/连接或块资源；同包不同 nodeId 完全独立。含包流程还需显式全局 budget；当前 Ollama/OpenAI 兼容适配器不保证严格 token 上限，严格模式拒绝，须由配置者明确选择非严格模式。

`POST /flows/validate-ports` 接受完整 FlowDraft，`POST /flows/validate` 接受 `{content: FlowDraft}` 并合并结构、连接、节点配置及有效输入样例检查。任何预检都不调用模型或创建任务。

端口 `source` 为 input/node/carry/constant，`target=[]` 代表完整输入；对象可按字符串字段路径装配，数组只支持整值装配。数组索引读取必须由 minItems 保证存在。缺省字段由输入契约明确约束，不做隐式结构转换。分支各自声明共同出口；循环外只可读取循环节点出口，零次返回 initial，carry.update 只影响下一轮。

无法证明的特殊约束拒绝连接；相同已加载契约允许连接，运行时仍必须执行自定义校验。issues 包含 nodeId、sourceNodeId、sourcePort、targetPort、fieldPath、reasonType、reason 和 expected，不含原始输入或异常 ctx。

## 生成完整实例（I7）

`POST /api/v1/services` 和 `POST /api/v1/services/{serviceId}/versions`
现在接收 `{ "name": "服务名", "flow": <FlowDraft> }`。将前文预检通过的完整
FlowDraft 原样放入 `flow`；不再提交旧 `definitionLoadId`／`definition`。
成功返回 201、`serviceId`、`activeInstanceId` 及 `current` 版本信息。

保存会预检全部端口、节点配置、环境和输入样例，编译 LangGraph 并固定内存内容，
不会调用块或模型。失败不创建半成品、不切换当前实例。
`GET /api/v1/services/{serviceId}/schema` 返回输入输出 Schema、`examples`、
完整 `flow`、`compilerVersion` 和各包节点配置 Schema。
纯块实例可省略 `budget` 和 `nodeConfigurations`，无需环境。

历史操作沿用 `GET /services/{serviceId}/versions` 和
`POST /services/{serviceId}/activate`（请求 `{ "instanceId": "ins_..." }`），均带 `/api/v1` 前缀。
新增 `GET /services/{serviceId}/versions/{instanceId}` 读取完整拼图及配置；
`POST /services/{serviceId}/versions/{instanceId}/draft` 将历史复制为新的可编辑草稿。
拓扑、契约或模块内容变化升大版本；仅节点参数、预算或环境绑定变化升小版本；
两类同时变化标记 `breaking`。回退保留原实例标识，重新校验并使用当前环境。
