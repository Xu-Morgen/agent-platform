# 最小文本查重

平台源码没有查重分支。`instance/` 组织严格输入→清洗→确定性计分→`packages/semantic/` 单次模型交互→组装两类报告；启动、加载、配置和调用见 [接入操作](../README.md)。

输入 `targetText` 和非空 `comparisonTexts` 字符串数组，不接受文件路径、未知字段或隐式类型转换。清洗统一 CRLF/CR 换行为 LF，Unicode NFC、折叠水平空白、去首尾空白和空段，每个非空行视为段落，保留大小写及标点。空白目标或对照按原始字段路径报错。

`quantitative.method=paragraph-exact-v1`。每个目标段落与对照任一段落完全相同才算匹配，similarity=匹配目标字符数/目标字符总数，按 Python Unicode 码点计数且不计换行。目标重复段落按位置计，对照重复不放大分值；matches 返回从 0 开始的段落索引。数字不是抄袭概率，也不做近似匹配。

`qualitative.items` 覆盖全部 comparisonIndex，每项 relation 为 similar / possible_paraphrase / no_clear_relation，附 reason 与 suggestion。模型不输出抄袭布尔结论；由教师综合判断。两类报告必须同时成功，模型错误不会转成定量部分成功。

示例 `examples/input.json` 的两个分值为 0.5、0；`examples/report-contract.json` 中定性部分是人工契约样例，不是真实模型结果。原始契约只维护 `instance/contracts.py`；修改后运行：

```bash
.venv/bin/python samples/assignment-similarity/sync_contracts.py
.venv/bin/python samples/assignment-similarity/sync_contracts.py --check
```

生成副本让语义包可以独立复制和快照加载，不依赖实例源路径。模型消息通过平台上下文发送，Prompt 从包快照读取；地址和凭据由平台环境配置注入。

用户提供的 artifact DOCX 仅用于本地计分测验，未将原文提交或发送至外部模型；PDF/XLSX 未作为文本查重标签或 AI 准确率评估。最终真实模型验收使用独立合成输入，证据以 [I5 任务卡](../../docs/tasks/i5.md) 为准。
