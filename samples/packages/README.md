# 创建业务包

业务包封装模型交互和必要前后处理。完整业务流程仍由服务拼图组织，包内不调度其他包。

## 创建步骤

1. 复制 [minimal/](minimal/README.md) 目录，修改 package.json 的 packageId/name/version。
2. 在 models.py 定义输入、输出 StrictModel，以及继承 PackageBudget 的 Config。
3. 在 package.json 的 contractRefs 中引用这些类型，在 entry 中引用实际函数。
4. 在 entry.py 实现 `invoke(value, config, context)`。调用前在 requiredCapabilities 中声明所需能力。
5. 在平台资源页加载整个目录，插入包节点，配置参数、预算和能力连接，再保存服务。

| 文件 | 最小实现 | 完整实现 | 作用 |
| --- | --- | --- | --- |
| package.json | 必需 | 必需 | 资源元数据、符号引用、依赖、能力、默认预算 |
| models.py | 必需 | 必需 | 本模板的业务输入输出、配置及能力契约 |
| entry.py | 必需 | 必需 | 本模板的执行函数 |
| prompt.txt | 无，Prompt 直接写在入口中 | 有 | 可维护的固定模型指令资源 |
| node-configuration.example.json | 说明材料 | 说明材料 | 节点配置示例，平台不会自动读取 |
| README.md | 说明材料 | 说明材料 | 输入输出和操作步骤 |

只有 package.json 是固定文件名；models.py 和 entry.py 可改名，只要同步清单中的 `module:Symbol`。例如 `entry:invoke` 指 entry.py 中的 invoke，`models:Text` 指 models.py 中导出的 Text。包内自有代码使用相对导入，如 `from .models import Text`。

页面加载时选目录，不选 package.json 文件。加载会检查已安装依赖、解析入口/模型、捕获目录内容；不会发起模型请求。目录不应含凭据、虚拟环境以外的大型数据或运行日志，快照会收集其中的资源文件。

## 两种模板

- [最小包](minimal/README.md)：一次模型调用，没有自定义业务配置；只需要模型连接。
- [完整包](complete/README.md)：嵌套业务配置、声明并使用三类能力、快照资源读取、检查点、业务输出验证和明确错误。需要额外加载最小通用块，并配置指导 API 连接。

**全部清单/节点/环境配置**见 [CONFIGURATION.md](CONFIGURATION.md)。**入口参数和全部上下文方法**见 [CONTEXT.md](CONTEXT.md)。加载、接线和外部调用见 [USAGE.md](../USAGE.md)。
