# 创建 Prompt 业务包

核对日期：2026-09-24。

业务包只维护输入输出契约、可选业务参数和 Prompt。平台负责验证、替换占位符、调用一次 LLM、验证并返回业务输出。数据清洗、转换、请求准备和结果加工使用流程中的通用块节点。

## 最小交付

```text
my-package/
├── package.json   # 身份、版本、输入输出契约引用
├── models.py      # 输入输出 StrictModel；按需添加 Config
└── prompt.txt     # 含 {{input.primary.text}} 等占位符的 Prompt
```

1. 复制 [minimal/](minimal/README.md)，修改 packageId/name。
2. 在 models.py 声明业务 Input/Output，以及继承 NodeInput[Input, tuple[...]] 的 Entry；contractRefs.input 引用 models:Entry，output 引用业务输出。零参考使用 tuple[()]。
3. 在 prompt.txt 编写任务指令和输入占位符。
4. 加载整个目录，将包插入服务，接线并选择模型连接；配置节点与任务预算后保存。

执行入口由平台提供，包没有自定义执行入口或独立依赖安装机制。契约使用平台已有的 StrictModel/Pydantic；只维护结构和验证规则，不在验证器里做数据转换、调用网络或处理业务流程。

`package.json` 为固定清单名；契约文件名由符号引用决定。Prompt 默认读取 prompt.txt，可用 prompt 字段改成包内相对路径。所有内容从内存快照读取。

最小模板没有 Config；[完整模板](complete/README.md)增加可选参数、嵌套配置和预算默认值。两者使用同一平台入口。节点配置示例和 README 是说明材料，不会自动执行。

[全部配置](CONFIGURATION.md) · [标准执行及占位符规则](CONTEXT.md) · [加载、接线和调用](../USAGE.md)

## 版本与升级

包目录中的代码、Prompt、README 等内容均参与摘要；修改后须递增版本并重新导入。排除目录、符号链接限制和包内相对导入见 [包目录快照](../../docs/resource-guide.md#包目录快照)。同版本冲突和实例升级遵循 [资源规则](../../docs/resource-guide.md#更新与归档资源)。旧字段对照见 [历史迁移说明](../../docs/archive/2026-09-24/legacy-resource-migration.md)。

模板版本见 [samples 入口](../README.md#版本与接线入口)，实际版本以 package.json 为准。
