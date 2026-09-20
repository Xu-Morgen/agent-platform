# 三类资源开发模板

这里按资源类型组织，每类只提供最小和最完整两套示例，共用说明文档放在对应目录。先复制最小实现，再按需要引入最完整示例中的能力与配置，不另设按功能拆分的第三套示例。所有示例对应当前平台源码，仅使用已经实现的接口。“最完整”指该类资源的配置与契约用法，不代表三个完整示例可以直接拼成同一流程。

| 你要创建什么 | 最小实现 | 最完整示例与配置说明 | 加载对象 |
| --- | --- | --- | --- |
| 通用块：确定性处理、转换、判断 | [blocks/minimal.py](blocks/minimal.py) | [blocks/README.md](blocks/README.md)、[complete.py](blocks/complete.py) | 一个 Python 文件 |
| 业务包：Prompt 与严格输入输出契约 | [packages/minimal/](packages/minimal/README.md) | [packages/complete/](packages/complete/README.md)、[配置参考](packages/CONFIGURATION.md)、[标准执行入口](packages/CONTEXT.md) | 包含 package.json 的目录 |
| 独立契约：定义端口的数据形状 | [contracts/minimal.py](contracts/minimal.py) | [contracts/README.md](contracts/README.md)、[complete.py](contracts/complete.py) | Python 文件 + 类型 symbol |

```text
samples/
├── README.md
├── USAGE.md                   # 加载、接线、保存、调用及完整公共字段说明
├── blocks/
│   ├── README.md              # 创建步骤、所有元数据、输入选项、扩展边界
│   ├── minimal.py             # 去掉首尾空白
│   └── complete.py            # API 查询与响应校验、嵌套选项、文本处理和统计
├── packages/
│   ├── README.md              # 创建步骤与文件职责
│   ├── CONFIGURATION.md       # 清单、节点、模型、预算、环境配置
│   ├── CONTEXT.md             # 平台入口、占位符、校验及错误处理
│   ├── minimal/              # 一次模型调用，仅三个运行必需文件
│   └── complete/             # 嵌套参数、Prompt 占位符、预算默认值
└── contracts/
    ├── README.md              # 输入输出、类型约束、校验钩子与兼容性
    ├── minimal.py             # 一个 text 字段
    └── complete.py            # 嵌套批次、可空字段、枚举、跨字段验证
```

## 三者的入口、出口和配置

| 项目 | 通用块 | 业务包 | 独立契约 |
| --- | --- | --- | --- |
| 执行入口 | 恰好一个 `@block` 函数 | 平台内置标准入口 | 无执行入口 |
| 输入、输出 | 函数参数与返回值的类型注解 | `contractRefs.input/output` | 所选 symbol 本身就是一个端口类型 |
| 可调业务参数 | 放进完整输入模型，由服务输入或上一层通用块提供 | Config 模型 + 节点 `parameters` | Field 默认值与约束，不是执行参数 |
| 扩展点 | 同步/异步函数、Pydantic 校验器 | Prompt 占位符、可选 Config、数据结构验证 | Pydantic 字段及模型校验器 |
| 预算、环境 | 普通块无节点配置；API 块绑定 API 连接并配置请求路径，无模型预算 | 节点绑定模型及预算，任务另设全局预算 | 无 |

**从 [USAGE.md](USAGE.md) 开始**：先运行不依赖模型的最小通用块，再加载最小业务包。完整业务包增加嵌套参数和预算默认值；数据处理通过通用块节点完成。

通用块的[最完整示例](blocks/README.md#最完整实现)包含 API 查询与文本处理；API 连接和请求路径配置在块节点上。最小文本块的输出可直接接入最小包。完整块需通过通用块提取 `text` 并输出完整的 `{text: ...}` 后接入最小包，因为其原输出还包含统计字段，平台不支持字段映射。完整包要求 `text` 为 1～10000 字符，现有块的输出没有这一保证，需先通过声明并验证该约束的转换块。完整独立契约演示批次结构，需配套处理节点，不能直接替换文本示例的端口。

约定：Python 字段使用 snake_case；对外 JSON 使用 camelCase。对象继承平台 StrictModel，拒绝未知字段和宽松类型转换。资源加载路径必须是后端能读取的本地路径；任务附件使用已保存的 TaskFile 引用，不接受本机路径字符串。

实际业务组合见 [文档出题实例](../examples/document-question-generation/README.md)：单文件读取块、本地 OCR、严格出题包及线上模型配置。实例独立交付，samples 继续只维护三类资源的最小/完整开发模板。

2026-09-17 按新的模板要求重建了整个 samples。原 template、assignment-similarity、流程导入/查重调用脚本已删除；旧内容仅能从 Git 历史查阅。当前目录没有查重产品、自动契约生成脚本或带占位符的流程导入协议。
