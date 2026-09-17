# 创建通用块

通用块是一个可独立加载的 `.py` 文件。无需 package.json，也没有 Config、环境绑定或上下文参数。

## 最小实现

复制 [minimal.py](minimal.py)，修改 `id`、`name` 和函数体。页面选择“单文件通用块”，加载复制后的文件。

```json
{"text": "  hello  "}
```

输出：

```json
{"text": "hello"}
```

函数 `trim(value: Text) -> Text` 的参数类型是入口，返回值类型是出口。Text 的 `text: str` 必填，允许空字符串；纯空白输入会得到空字符串。平台先验证输入，再调用函数，最后验证返回值。

也可以直接用 `str`、`bool` 等类型，例如 `def is_ready(value: str) -> bool`；这时输入是 JSON 字符串，输出是 JSON 布尔值。条件块必须返回严格 bool，不能用 0/1 替代。

## 完整实现

[complete.py](complete.py) 展示一个入口内的确定性处理和明确输出。执行顺序为去掉首尾空白 → 合并空白 → 大小写转换 → 添加前缀 → 计算统计。

```json
{
  "text": "  Hello\n  World  ",
  "options": {
    "trimEdges": true,
    "collapseSpaces": true,
    "letterCase": "upper",
    "prefix": "> "
  }
}
```

输出：

```json
{"text": "> HELLO WORLD", "characterCount": 13, "changed": true}
```

| 输入配置 | 默认值/约束 | 作用 |
| --- | --- | --- |
| `text` | 必填，1～10000 字符 | 原始文本 |
| `options` | 可省略，生成 Options 默认实例 | 此次执行选项；不是节点 parameters |
| `options.trimEdges` | true | 去掉首尾空白 |
| `options.collapseSpaces` | true | 连续空白含换行合并为一个空格 |
| `options.letterCase` | preserve；可选 lower/upper | 转换字母大小写 |
| `options.prefix` | 空字符串，最长 20 字符 | 在其他处理完成后添加前缀 |

| 出口字段 | 类型 | 含义 |
| --- | --- | --- |
| `text` | str | 处理后的文本，允许为空 |
| `characterCount` | int ≥ 0 | 处理后文本的 Unicode 码点数，包含前缀 |
| `changed` | bool | 最终文本是否与原输入不同 |

例如只传 `{"text":" A  B "}`，输出为 `{"text":"A B","characterCount":3,"changed":true}`。传 `{"text":12}` 或 `{"text":"x","unknown":true}` 会在入口校验时失败。字段范围约束也会在执行前验证。

## @block 的全部配置

| 参数 | 是否必填/默认 | 作用 |
| --- | --- | --- |
| `id` | 必填 | 资源身份，以英文字母开头，仅字母、数字、下划线、连字符 |
| `version` | 必填 | `1.0.0` 或 `1.0.0-alpha` 格式；同会话内同 id/version 不允许内容不同 |
| `name` | 必填，非空 | 页面展示名称 |
| `description` | 默认空字符串 | 用途说明，不影响执行 |
| `dependencies` | 默认空列表 | 已安装第三方依赖的 PEP 508 版本声明；例如 `['httpx>=0.28,<1']` |

标准库、agent_platform 和 pydantic 无需在块的 dependencies 中额外声明。其他第三方导入必须声明且已安装，加载器只检查、不安装；不支持 URL/extras 依赖。修改文件任意内容都会影响摘要，包括注释；同会话重新加载修改版时应更新 version。

## 可以使用的函数与校验钩子

- 一个文件必须恰好有一个注册函数，可包含未装饰的辅助函数及多个模型。
- 函数只接受一个无默认值的位置参数，参数和返回值都必须有类型注解。不支持 `*args`、`**kwargs` 或第二个 context 参数。
- `def run(value: Input) -> Output` 和 `async def run(value: Input) -> Output` 都可以。平台会等待异步结果；async 本身不会使 CPU 计算可抢占。
- 模型可使用 Pydantic `field_validator`、`model_validator`；完整写法见 [契约示例](../contracts/README.md)。入口含自定义校验时，接线会受到契约身份限制。
- 没有 on_load、before_run、after_run、on_error、on_cancel 注册钩子。前后处理写在函数内；需要局部资源清理时使用 Python `try/finally`。

独立文件只快照自身源码，不能相对导入邻接自有文件。把自有类型和辅助函数一起放入文件。加载会导入顶层代码，因此顶层只放声明，不启动请求或修改外部状态。

平台没有给块注入 `call_model`、能力绑定或凭据接口；模型交互应使用业务包。普通异常会使步骤失败；如需明确的业务错误，抛出平台 `PlatformError(ErrorResponse(...))`，示例见 [业务包上下文](../packages/CONTEXT.md)。不要返回伪造成功值。

## 输入参数怎么固定

块的选项是输入，不在 `nodeConfigurations` 中填写。可以让服务输入包含整个 Input，也可以用接线常量固定选项。例如完整块节点：

```json
{
  "nodeId": "normalize",
  "kind": "block",
  "artifactRef": "替换为加载完整块返回的 resourceId",
  "inputs": [
    {"target": ["text"], "source": {"kind": "input", "path": ["text"]}},
    {"target": ["options"], "source": {"kind": "constant", "value": {"letterCase": "upper"}}}
  ]
}
```

其余选项由 Options 默认值补齐；服务输入的 text 仍须满足块的长度约束。最容易成功的接法是直接选择此块返回的 inputContract/outputContract 作为服务端口，并采用完整输入/输出接线，见 [公共用法](../USAGE.md)。
