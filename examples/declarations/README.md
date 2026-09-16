# 声明校验样例

`package.json` 与 `instance.json` 只演示声明契约，符号引用是示意，尚非可调用模型业务产品。完整可执行模板属于 I5-T06。

- Python 权威模型在 `contracts/packages.py` 与 `contracts/instances.py`；用 `export_schema(Model)` 导出公开 camelCase Schema。
- 包声明入口与三个模型引用、运行要求和能力契约；具体配置模型继承 `PackageBudget` 并可添加配置字段。当前只校验声明格式，运行时兼容性和引用解析由加载/配置任务负责。
- 实例固定包版本和配置 revision；scope 为 `instance` 或 `packages.<bindingId>`。同作用域重复顶层字段拒绝，不做隐式合并覆盖。
- 实例预算显式保存；后续配置表单按包预算之和提供全局默认值。本阶段不执行预算策略。
- 环境字段只保存标识，不保存凭据或硬编码连接地址。
