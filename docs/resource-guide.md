# 三类资源指导手册

本文对应当前 V1 实现。先从通用块开始，再引入业务包；独立契约用于约束服务及容器端口。资源优化的未实现项目见 [专项计划](resource-plan.md)。

## 1. 选择资源类型

| 类型 | 适用工作 | 最小交付 | 在拼图中的位置 |
| --- | --- | --- | --- |
| 单文件通用块 | 清洗、转换、计分、确定性判断 | 一个带 `@block` 的 `.py` | 可执行节点，也可满足包声明的块能力 |
| 业务包 | 带 Prompt 和业务输出约束的模型交互 | `package.json`、入口、模型与资源 | 可执行节点，逐节点配置 |
| 独立契约 | 声明服务输入输出、分支出口、循环携带值 | `.py` 文件中的一个类型 symbol | 端口类型，不执行业务逻辑 |

包需要模型/API/块能力时，通过声明和节点配置绑定。环境、服务实例和这些资源分开管理；环境不是第四类拼图资源。

## 2. 单文件通用块

复制 [字段转换块](../samples/template/blocks/rename.py)，最小结构如下：

```python
from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel

class Input(StrictModel):
    legacy_text: str

class Output(StrictModel):
    text: str

@block(id='rename-text', version='1.0.0', name='字段转换',
       description='将 legacyText 显式转换为 text')
def convert(value: Input) -> Output:
    return Output(text=value.legacy_text)
```

JSON 输入 `{"legacyText":"你好"}`，输出 `{"text":"你好"}`。字段别名来自 StrictModel。整数不能冒充字符串，未知字段会被拒绝。

编写要求：

1. 一个文件恰好一个注册函数，只有一个无默认值参数，输入与返回值均须类型注解；支持同步或异步入口。
2. 对象继承 StrictModel，嵌套对象也使用严格模型。简单类型可直接使用 bool、str 等支持的 JSON 类型。
3. 函数及自有类型在单文件中，不相对导入旁边文件。第三方依赖在装饰器 `dependencies` 中声明版本范围；加载器检查但不安装依赖。
4. 加载时会导入模块，顶层不执行业务请求。块不直接管理平台任务、模型连接或凭据。
5. 同一 id/version 对应固定内容。更新已加载内容须更新版本；旧任务继续执行原快照。

页面操作：资源类型选择“单文件通用块”，填后端可读的文件绝对路径；选择它的输入和输出契约，插入节点，把完整服务输入接到完整节点输入，把节点完整输出接到服务出口。保存实例后在任务页提交上述输入。

其他指导样例：[文本透传](../samples/template/blocks/text.py)、[严格 bool 条件](../samples/template/blocks/condition.py)、[LMS 解包](../samples/template/blocks/lms.py)。LMS 块只输出声明的 Payload，失败业务码不会伪装为成功数据。

## 3. 业务包

复制 [标准包目录](../samples/template/packages/example/package.json)。文件职责：

| 文件 | 维护内容 |
| --- | --- |
| package.json | 标识、版本、入口、输入输出/配置引用、运行依赖、能力要求和预算默认值 |
| entry.py | `async def invoke(value, config, context)`；调用能力并返回业务输出 |
| models.py | 业务参数及平台模型请求/响应类型 |
| contracts.py | 业务输入输出类型的分发副本 |
| prompt.txt | 通过 context.read_resource 读取的固定资源 |

清单里的 `entry:invoke` 指向 entry.py 的 invoke；`models:Message` 指向 models.py 导出的 Message。完整可用清单见模板，不自行省略运行依赖或能力契约。入口示意：

```python
from .models import ModelRequest

async def invoke(value, config, context):
    response = await context.call_model('chat', ModelRequest(messages=[
        {'role': 'system', 'content': context.read_resource('prompt.txt').decode('utf-8')
         + '\n' + config.instruction},
        {'role': 'user', 'content': value.text},
    ], max_output_tokens=config.max_output_tokens))
    return response.output
```

包不能硬编码 Base URL、API Key 或环境 ID。平台先校验业务输入和配置，包通过已声明的 chat 能力取得模型响应，平台再校验业务输出。返回不符合 Message 的对象会失败；不得用固定成功文本掩盖模型错误。

页面操作：先创建模型环境，再加载业务包目录并插入节点。节点配置窗填写 instruction 和 maxOutputTokens；分别设置 loopLimit/tokenLimit，chat 选择环境及 model 连接。全局也配置预算，当前适配器显式关闭严格 token 模式。

复制 [同包双节点配方](../samples/template/flows/two-packages.json)可展示不同节点独立配置：第一节点概括，第二节点按前序输出提出建议。每次包调用尝试计一轮 loop，循环中累计，失败尝试也计数；loop 不是 LangGraph 步数或 while 次数。当前没有自动重试。

API 与块能力使用相同声明/绑定思路，通过 `context.call_capability` 调用；完整业务顺序由拼图组织，不在包内再写实例入口或调度其他包。

## 4. 独立契约

现成独立文件为 [flows/contracts.py](../samples/template/flows/contracts.py)：

```python
from pydantic import Field
from agent_platform.contracts.base import StrictModel

class Message(StrictModel):
    text: str = Field(min_length=1)
```

页面选择“契约文件”，路径填此文件绝对路径，symbol 填 `Message`（不填 `文件名:Message`）。选择加载后的 Message 作为服务输入、输出或控制容器的出口/携带值。契约资源不能插入为业务节点，也不会自动生成字段转换逻辑。

等价 HTTP 请求：

```json
{"kind":"contract","path":"/absolute/path/contracts.py","symbol":"Message"}
```

提交到 `POST /api/v1/catalog/load`，返回的 `resourceId` 用作 `inputContract` / `outputContract`；契约资源本身没有模块的 inputContract 字段。[顺序配方](../samples/template/flows/sequence.json)直接演示此引用。

静态兼容检查验证字段结构、必填与可空、支持的类型约束及引用作用域；运行时继续严格校验值。Python 自定义校验器不能只靠外观相同的 JSON Schema 证明等价，平台会保守检查其来源；不兼容时使用明确转换块。

共享业务契约只维护一个权威源：模板的 `flows/contracts.py` 通过 `sync_contracts.py` 生成包内副本。查重权威源位于 `source/contracts.py`。生成副本用于独立分发和快照，不能改成运行时随意读取邻接目录。契约演进时同时审查上下游节点、配置表单和样例配方。

## 5. 顺序、条件和循环

顺序接线可引用服务输入、可见的前序节点输出、常量；字段结构不匹配必须转换。不能越过分支作用域直接取内部分支节点的输出。

if 的条件必须是严格 bool，两条分支显式绑定共同出口。repeat 明确次数，0 次返回初始携带值。while 使用返回 bool 的块作为条件，明确 maxIterations；条件仍为真而达到上限时失败。循环体引用 carry，显式配置 initial 与 update，循环结束仅从循环出口取值。

完整配方和预期行为见 [模板说明](../samples/template/README.md)。纯块流程无需预算和环境；含业务包时同时设置节点与全局预算。无限循环、任意表达式和自由画布不在 V1 范围。

## 6. 保存与外部调用

| 操作 | API |
| --- | --- |
| 加载/查看资源 | POST /api/v1/catalog/load；GET /api/v1/catalog |
| 草稿保存/更新 | POST /api/v1/drafts；PUT /api/v1/drafts/{draftId}，请求 `{content: FlowDraft}`，可保存未完成内容 |
| 预检 | POST /api/v1/flows/validate，请求 `{content: FlowDraft}` |
| 保存服务 | POST /api/v1/services，请求 `{name, flow: FlowDraft}` |
| 保存新版本 | POST /api/v1/services/{serviceId}/versions，请求同上 |
| 获取业务契约 | GET /api/v1/services/{serviceId}/schema |
| 提交任务 | POST /api/v1/runs，请求 `{serviceId, input}`，可带 expectedInstanceId |
| 查询/结果 | GET /api/v1/runs/{runId}；GET /api/v1/runs/{runId}/result |
| 取消 | POST /api/v1/runs/{runId}/cancel |

具体字段和响应以正在运行的 `/docs` 为准。`flows/*.json` 是包含资源清单的教学配方，须用 `samples/flow_templates.py` 解析占位符后才是 FlowDraft。草稿不能直接调用，实例保存成功才切换稳定服务入口。

常见排查：缺少 symbol 检查独立契约加载配置；端口不兼容查看 nodeId/fieldPath 并增加转换；环境占用时等待任务终态；TOKEN_ACCOUNTING_UNSUPPORTED 检查严格模式选择；模型输出失败检查 Prompt 与业务输出契约，不以取消或默认值掩盖错误。
