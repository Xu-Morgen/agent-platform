# I2 配置与版本样例

本目录使用合成数据，只验证配置、内容快照、图构造和版本管理，不代表真实模型或任务执行已完成。

在桌面服务配置区依次加载：

| 类型 | 路径 | 标识 |
| --- | --- | --- |
| block | examples/configuration/block | identity@1.0.0 |
| package | examples/configuration/package | echo@1.0.0 |
| package | examples/configuration/second | second@1.0.0 |
| instance | examples/configuration/instance | two-packages |

实例定义中的两个包绑定各有一个配置，能力绑定指向固定块版本；无远端连接需求。默认全局预算为各包局部预算求和：loop=4、token=200。此处预算只声明与校验，执行控制属于 I4。

API 统一前缀 `/api/v1`，FastAPI `/docs` 提供权威请求响应 Schema：

- `POST /registry/load`：`{"kind":"block","path":"examples/configuration/block"}`，返回 id/version/digest/schemas；实例还返回 loadId、definition、configuration、budgetDefaults。
- `POST /services`：`{"name":"合成服务","definitionLoadId":"加载返回的 loadId","definition":加载返回的 definition}`。不要将响应原样当作请求。
- `POST /services/{serviceId}/versions`：同创建请求；成功生成新实例并立即切换，失败不影响当前版本。
- `GET /services`、`GET /services/{serviceId}/schema`：稳定标识、当前实例和契约。
- `GET /services/{serviceId}/versions`：本次会话历史。
- `POST /services/{serviceId}/activate`：`{"instanceId":"历史中的原 instanceId"}`；重新验证当前环境，不生成版本。
- `POST /environments`：`{"name":"合成环境","connections":[{"connectionId":"model","kind":"model","baseUrl":"http://localhost:9000","model":"synthetic","credential":"synthetic-only","timeoutSeconds":60}]}`，响应仅包含 credentialRef。`PUT /environments/{environmentId}` 使用同一写入格式，保留引用即可保留凭据。

同一包／块版本加载不同内容会被拒绝，修改内容需修改声明 version。实例每次加载有独立句柄；保存时固定句柄对应的内存内容，编辑原文件不会改变旧实例。配置在 `configRefs` 中按作用域合并，同字段冲突明确报错；能力绑定的包、块与环境引用必须可用。

包的 configuration 模型继承 `PackageBudget`；自有 Python 模块使用相对导入。实例 `workflow` 指向无参工厂，返回 I1 `build_sequential` 创建的 `SequentialExecutor`。本地源码受信任，加载不是沙箱，不自动安装依赖。
