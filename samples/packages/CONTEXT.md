# 执行入口与可用钩子

## 平台调用顺序

加载时导入入口和类型；保存服务时验证配置与绑定。每次执行包时，平台检查预算和取消状态，严格验证业务输入/配置，然后调用清单 entry 指向的函数，最后验证业务输出并记录步骤结果。

```python
async def invoke(value, config, context):
    ...
    return output
```

| 参数/返回值 | 实际类型及用途 |
| --- | --- |
| value | contractRefs.input 指向的模型实例，使用 `value.text` 取值 |
| config | contractRefs.configuration 指向的模型实例；合并节点 parameters 和 budget 后验证所得 |
| context | 平台 PackageContext，仅提供下面列出的公共方法 |
| 返回值 | 符合 contractRefs.output 的模型或字典，不返回整个 ModelResponse |

同步入口也支持，返回 awaitable 时平台会等待。与块不同，包入口的输入/输出契约以清单为准，不从函数类型注解推导。三个参数按位置传入，函数名可改但需同步 entry。加载器检查可调用性，不会替你验证所有入口签名问题。

## PackageContext 的全部公共方法

| 方法 | 返回值 | 作用及限制 |
| --- | --- | --- |
| `await context.call_model(capability_id, request)` | ModelResponse | 调用已声明且绑定的 model 能力；request 为平台 ModelRequest 或符合该契约的数据 |
| `await context.call_capability(capability_id, value)` | 该能力 outputModel 实例 | 调用已声明的 model/api/block 能力；输入输出均受契约校验 |
| `context.read_resource(name)` | bytes | 读取当前包固定内容快照中的文件，例如 `prompt.txt`；自行 UTF-8 解码 |
| `await context.record_progress(step_id, message)` | None | 触发名为 progress 的运行边界检查；当前 message 不保存、不展示，不生成百分比或自定义 StepRecord |

capability_id 对应清单中的 capabilityId，不是环境 connectionId；未声明或类型不符会报 DEPENDENCY_ERROR。只有模型/API/块能力，不能用 context 调用另一个包或直接改任务状态。

read_resource 使用规范包内相对路径，不允许绝对路径和 `..`。包源码通过内存导入，`__file__` 不是可供 open 的真实文件路径；使用快照资源保证提交后的任务不受源文件改动影响。

## 模型请求与响应的所有字段

| 字段 | 作用 |
| --- | --- |
| ModelRequest.messages | 至少一条消息 |
| messages[].role | system/user/assistant |
| messages[].content | 字符串内容，不支持多模态消息数组 |
| ModelRequest.maxOutputTokens | 正整数，本次请求输出 token 上限 |
| ModelResponse.output | JSON 值；模型协议层不会自动知道业务输出模型 |
| ModelResponse.usage.inputTokens / outputTokens | 非负计数；无法计量时可能为 null |
| ModelResponse.usage.quality | exact / upper_bound / estimated / unsupported |
| ModelResponse.usage.source | 计量来源说明 |

业务包只构造请求，usage 由平台适配器返回并核算。完整示例先把 response.output 验证为 ModelSummary，再检查配置驱动的关键词数量上限；平台最后还会验证包的 Output。不要把 usage 字段添加到业务输出中，除非显式扩展业务契约。

## 可用的校验及处理钩子

- `@field_validator`：验证一个字段，例如配置 instruction 不能全为空白。
- `@model_validator`：验证跨字段关系，见 [完整独立契约](../contracts/complete.py)。
- invoke 中的前处理：调用块能力、构造请求或查询必要上下文。
- invoke 中的后处理：验证模型 JSON、明确检查动态约束、组装业务输出。
- 局部资源清理：普通 Python `try/finally`，不注册平台全局清理逻辑。

**平台未提供可注册的 on_load/on_start/on_finish/on_error/on_cancel 钩子，也没有清单 hooks 字段。** runtime 内部 Boundary 的 observer/policies 由平台管理，不是给包修改的扩展接口。record_progress 只提供一个主动检查点；无法用它中断正在执行的同步 CPU 代码。

## 错误和取消

模型/API 的传输错误和运行时校验错误应向上传播；不要捕获后返回固定成功内容。需要明确业务错误时：

```python
from agent_platform.contracts.errors import ErrorResponse, PlatformError

raise PlatformError(ErrorResponse(
    code='OUTPUT_VALIDATION_ERROR',
    stage='sample.summary',
    message='关键词数量超过节点配置的上限',
    field_path=['keywords'],
))
```

普通异常也会使步骤失败，但平台会隐藏异常正文并返回通用错误。message 应说明可操作原因，不放原始输入、模型响应或凭据。校验位置和 code 使用当前平台错误契约支持的值。

主动取消等待当前模型传输结束再完成；等待中超时/断连优先记失败。关闭应用立即停止本地传输。包无需自行管理取消状态，不应吞掉取消或预算异常。没有自动重试和恢复；同一任务在拼图循环中多次进入包会累计调用次数与 token。
