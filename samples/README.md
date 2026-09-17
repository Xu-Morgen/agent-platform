# 三类资源开发模板

这里按资源类型组织，每类各有一个最小实现和一个完整示例。先复制最小实现，再按需要引入完整示例中的配置。所有示例对应当前平台源码，完整示例仅使用已经实现的接口。

| 你要创建什么 | 最小实现 | 完整示例与配置说明 | 加载对象 |
| --- | --- | --- | --- |
| 通用块：确定性处理、转换、判断 | [blocks/minimal.py](blocks/minimal.py) | [blocks/README.md](blocks/README.md)、[complete.py](blocks/complete.py) | 一个 Python 文件 |
| 业务包：模型交互及必要的前后处理 | [packages/minimal/](packages/minimal/README.md) | [packages/complete/](packages/complete/README.md)、[配置参考](packages/CONFIGURATION.md)、[上下文接口](packages/CONTEXT.md) | 包含 package.json 的目录 |
| 独立契约：定义端口的数据形状 | [contracts/minimal.py](contracts/minimal.py) | [contracts/README.md](contracts/README.md)、[complete.py](contracts/complete.py) | Python 文件 + 类型 symbol |

```text
samples/
├── README.md
├── USAGE.md                   # 加载、接线、保存、调用及完整公共字段说明
├── blocks/
│   ├── README.md              # 创建步骤、所有元数据、输入选项、扩展边界
│   ├── minimal.py             # 去掉首尾空白
│   └── complete.py            # 嵌套输入、枚举、默认值、输出统计
├── packages/
│   ├── README.md              # 创建步骤与文件职责
│   ├── CONFIGURATION.md       # 清单、节点、能力、预算、环境配置
│   ├── CONTEXT.md             # 入口、上下文方法、校验及错误处理
│   ├── minimal/              # 一次模型调用，仅三个运行必需文件
│   └── complete/             # 模型/API/块能力、嵌套参数、Prompt、业务输出校验
└── contracts/
    ├── README.md              # 输入输出、类型约束、校验钩子与兼容性
    ├── minimal.py             # 一个 text 字段
    └── complete.py            # 嵌套批次、可空字段、枚举、跨字段验证
```

## 三者的入口、出口和配置

| 项目 | 通用块 | 业务包 | 独立契约 |
| --- | --- | --- | --- |
| 执行入口 | 恰好一个 `@block` 函数 | `package.json` 的 `entry` | 无执行入口 |
| 输入、输出 | 函数参数与返回值的类型注解 | `contractRefs.input/output` | 所选 symbol 本身就是一个端口类型 |
| 可调业务参数 | 放进输入模型，通过输入/常量接线 | Config 模型 + 节点 `parameters` | Field 默认值与约束，不是执行参数 |
| 扩展点 | 同步/异步函数、Pydantic 校验器 | 入口、上下文能力调用、资源读取、检查点、校验器 | Pydantic 字段及模型校验器 |
| 预算、环境 | 无节点配置 | 节点绑定能力及预算，任务另设全局预算 | 无 |

**从 [USAGE.md](USAGE.md) 开始**：先运行不依赖模型的最小通用块，再加载最小业务包。完整业务包增加 API 和块能力，所需外部接口与输入输出均有明确说明。

约定：Python 字段使用 snake_case；对外 JSON 使用 camelCase。对象继承平台 StrictModel，拒绝未知字段和宽松类型转换。路径必须是后端能读取的本地路径。

2026-09-17 按新的模板要求重建了整个 samples。原 template、assignment-similarity、流程导入/查重调用脚本已删除；旧内容仅能从 Git 历史查阅。当前目录没有查重产品、自动契约生成脚本或带占位符的流程导入协议。
