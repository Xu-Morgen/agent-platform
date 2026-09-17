# 创建独立契约

独立契约是单个 Python 文件中导出的一个类型。它定义数据的合法形状，不是执行函数，不需要 `@block`、package.json、Config 或环境。

## 最小实现和加载方法

复制 [minimal.py](minimal.py)，修改 Text 模型。最小合法数据：

```json
{"text": "hello"}
```

页面选择“契约文件”，填文件路径，symbol 填 **Text**。HTTP 等价请求：

```json
{"kind":"contract","path":"/absolute/path/minimal.py","symbol":"Text"}
```

发送到 `POST /api/v1/catalog/load`。以返回的 **resourceId** 作为服务 inputContract/outputContract，或分支 outputContract、循环 carry.contract。独立契约的 schemas.value 描述其类型；没有可执行节点的入口/出口引用。

`symbol` 是文件顶层的类型名称，不填 `minimal:Text`。同一文件可有多个类型，每次只加载所选类型。类名 Input 和 Output 只是命名约定，不会自动关联或自动加载。

## 完整输入与输出

[complete.py](complete.py) 提供 Input 和 Output，分别按 symbol 加载。Input 示例：

```json
{
  "items": [{"itemId": "part-1", "text": "示例文本"}],
  "note": null,
  "language": "zh",
  "minScore": 0.2,
  "maxScore": 0.8,
  "labels": ["demo"]
}
```

合法 Output 示例（仅描述形状，契约本身不会算分）：

```json
{
  "results": [{"itemId": "part-1", "score": 0.6, "accepted": true}],
  "summary": "一项结果",
  "reviewerNote": null
}
```

| 字段 | 必填/默认与约束 | 意义 |
| --- | --- | --- |
| Input.items | 必填，1～20 项 | 严格嵌套 Item 列表 |
| Item.itemId | 必填，`^[a-z][a-z0-9-]{0,31}$` | 批次内唯一标识 |
| Item.text | 必填，1～2000 字符，不能全为空白 | 条目正文 |
| Input.note | **必填**，str 或 null | 可空不等于可省略 |
| Input.language | 默认 zh，可选 zh/en | 输出语言声明 |
| Input.minScore / maxScore | 默认 0.0 / 1.0，有限数值且在 [0,1] | 范围声明，min 不大于 max |
| Input.labels | 默认新空列表，最多 5 项，每项非空 | 附加标签 |
| Output.results | 必填，1～20 项 | 执行节点生成的结果列表 |
| Result.itemId | 与 ItemId 相同的格式约束 | 结果标识；是否覆盖输入条目需执行节点检查 |
| Result.score | 必填，有限数值且在 [0,1] | 结果分数；是否落入输入指定范围需执行节点检查 |
| Result.accepted | 必填，严格 bool | 执行节点生成的布尔结果 |
| Output.summary | 必填，非空字符串 | 说明 |
| Output.reviewerNote | 默认 null，可省略 | 可选备注 |

以下输入会失败：未知字段、字符串 `"0.5"` 充当数字、缺少 note、重复 itemId、纯空白正文、minScore 大于 maxScore。Output 校验只能看到 Output 本身；不能凭这两个独立模型保证输入输出一一对应。

## 类型、字段配置和校验钩子

| 写法 | 作用 |
| --- | --- |
| `class X(StrictModel)` | 严格类型、禁止额外字段、默认值及赋值校验；嵌套对象也须继承它 |
| `str/int/float/bool/None` | JSON 标量；float 接受合法数值，不把数字字符串转为数字 |
| `list[T]`、`dict[str, T]` | 有明确元素类型的数组和字符串键对象 |
| `Literal['zh','en']` | 枚举；也可用 JSON 标量枚举 |
| `T | None` | 可空；是否可省略取决于是否提供默认值 |
| `Annotated[T, Field(...)]` | 可复用类型约束，例如 ItemId 和 Score |
| `Field(default=...)` | 可省略字段的默认值，不会替换显式 null |
| `Field(default_factory=...)` | 每次生成独立列表/嵌套配置 |
| `min_length/max_length` | 字符串长度或列表项数 |
| `ge/le/gt/lt` | 数值边界 |
| `pattern` | 字符串正则约束 |
| `allow_inf_nan=False` | 拒绝无穷与 NaN |
| `description`、`title`、`examples` | JSON Schema 中的说明元数据，不代表页面自动完整呈现 |
| `alias` | 显式对外名称；通常直接用默认 camelCase 即可 |
| `@field_validator('field')` | 单字段验证；完整示例拒绝纯空白 text |
| `@model_validator(mode='after')` | 字段解析完成后的联合验证；完整示例检查分数范围、ID 唯一性 |

默认模型还会校验赋值及默认值，校验器应无 I/O、无副作用，可重复运行。示例使用校验器拒绝非法值，不隐式清洗它们。`before`/`wrap` 等属于 Pydantic 校验扩展，不是平台生命周期钩子；若自行使用，仍须保持严格输入输出语义。

支持的类型由平台 strict_adapter 决定：不要用 Any、裸 dict/list、普通宽松 BaseModel、datetime、自定义任意对象或非字符串键字典。确实需要任意 JSON 时可用 Pydantic JsonValue，但它无法替代明确业务结构。最小类型也可直接导出 `Ready = bool`，然后加载 symbol `Ready`。

## 静态接线和运行时验证

平台先比较出口与入口的结构、必填、额外字段、枚举、数值/长度范围等，再在运行时验证实际值。宽松 `str` 不能直接连到要求 `minLength=1` 的入口，即使某次值碰巧非空。

Python 自定义校验器和 `allow_inf_nan=False` 会使目录契约带有运行时约束标识。两个不同来源的相似 Schema 不足以证明规则等价。需要完整相同的契约引用，或者用明确转换块输出目标类型，并让下游使用该块发布的 outputContract。将原独立文件再复制到块中，会得到不同的契约身份，不能只凭类名相同强行接线。

文件只快照自身内容。自有类型应放在同一文件，不导入邻接业务源码；不把包内含相对导入的 models.py 当作独立契约加载。无自定义校验的最小 Text 在三类模板中有意分别定义，以便独立复制；它们按结构兼容。生产共享契约应另行确定唯一权威源及分发流程，修改后同时检查上下游，当前模板不引入生成器。

独立契约没有 id、version、dependencies 清单或执行钩子。资源标识由文件摘要和 symbol 生成，改动文件会产生新身份；已有实例保留旧快照。依赖必须已存在于后端环境。
