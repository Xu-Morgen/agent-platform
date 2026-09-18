# 最小 Prompt 包

仅三个运行必需文件：package.json、models.py、prompt.txt。输入输出均为 `{ "text": "字符串" }`，没有 Config、业务入口、能力声明或包依赖。

Prompt 使用 `{{input.text}}`；平台调用一次模型，严格验证返回的 text 字段。模型返回数字、额外字段或非 JSON 内容会失败。

1. 加载当前目录。
2. 将包放入服务，选包的输入输出契约并接线。
3. 选择模型连接；parameters 保持空对象。
4. 节点预算默认 loopLimit=4/tokenLimit=32768，单次输出上限默认 512；上层文档的[节点配置示例](../CONFIGURATION.md#最小包节点配置示例)演示显式设置为 256。
5. 设置节点和任务的 loop/token 限额；用量按模型实际返回累计，超额停止后续步骤。
6. 保存服务并提交 `{"text":"需要概括的文本"}`。

[清单](package.json) · [完整配置](../CONFIGURATION.md) · [标准入口](../CONTEXT.md)
