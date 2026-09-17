# 最小文本查重

平台源码没有查重分支。`flows/similarity.json` 组织严格输入→`blocks/clean.py`→`score.py`→`adapt.py`→`packages/semantic/` 单次模型交互→`assemble.py` 双报告组装；实例由平台编译生成，`instance/` 仅保留既有契约/算法权威源和旧基线资料；启动、加载、配置和调用见 [接入操作](../README.md)。

输入 `targetText` 和非空 `comparisonTexts` 字符串数组，不接受文件路径、未知字段或隐式类型转换。清洗统一 CRLF/CR 换行为 LF，Unicode NFC、折叠水平空白、去首尾空白和空段，每个非空行视为段落，保留大小写及标点。空白目标或对照按原始字段路径报错。

`quantitative.method=paragraph-exact-v1`。每个目标段落与对照任一段落完全相同才算匹配，similarity=匹配目标字符数/目标字符总数，按 Python Unicode 码点计数且不计换行。目标重复段落按位置计，对照重复不放大分值；matches 返回从 0 开始的段落索引。数字不是抄袭概率，也不做近似匹配。

`qualitative.items` 覆盖全部 comparisonIndex，每项 relation 为 similar / possible_paraphrase / no_clear_relation，附 reason 与 suggestion。模型不输出抄袭布尔结论；由教师综合判断。两类报告必须同时成功，模型错误不会转成定量部分成功。

示例 `examples/input.json` 的两个分值为 0.5、0；`examples/report-contract.json` 中定性部分是人工契约样例，不是真实模型结果。原始契约只维护 `instance/contracts.py`；修改后运行：

```bash
.venv/bin/python samples/assignment-similarity/sync_contracts.py
.venv/bin/python samples/assignment-similarity/sync_contracts.py --check
```

生成副本让语义包可以独立复制和快照加载，不依赖实例源路径。模型消息通过平台上下文发送，Prompt 从包快照读取；地址和凭据由平台环境配置注入。

用户提供的 artifact DOCX 仅用于本地计分测验，未将原文提交或发送至外部模型；PDF/XLSX 未作为文本查重标签或 AI 准确率评估。最终真实模型验收使用独立合成输入，新版证据以 [I8 任务卡](../../docs/tasks/i8.md) 为准。

真实验收输入为 `examples/acceptance-1v6.json`，七篇各约 1560 字的合成文本；本地输入检查命令为 `.venv/bin/python checks/similarity_acceptance_input.py`。真实模型环境当前缺失，I8-T09/M2 状态见 [任务卡](../../docs/tasks/i8.md#i8-t09)。

## 新版服务页面接线

加载 `blocks/` 的四个单文件和 `packages/semantic`。服务输入选择“查重清洗 · 输入”，输出选择“查重报告组装 · 输出”；顺序插入清洗、计分、适配、语义、组装。

| 节点 | 入口来源 |
| --- | --- |
| 清洗 | 服务输入完整值 |
| 计分 | 清洗完整输出 |
| 适配 | 清洗完整输出（显式前序引用） |
| 语义 | 适配完整输出 |
| 组装 request | 服务输入完整值 |
| 组装 quantitative | 计分完整输出 |
| 组装 qualitative | 语义完整输出 |
| 服务出口 | 组装完整输出 |

组装节点分别添加三条接线并选择目标字段。点击语义包配置参数、loop=1、token=32768 和已保存的 model 环境连接；全局预算同上，当前适配器显式选择非严格模式。输入样例复制 `examples/input.json`，校验保存后到任务页调用。

单文件块由 `.venv/bin/python samples/assignment-similarity/generate_blocks.py` 生成，`--check` 检查漂移。计分直接复用原函数 AST，清洗保持原规则；生成的传输结构与权威报告校验分开：组装块明确执行跨字段覆盖校验，不宣称不同 Python 自定义校验器静态等价。块可独立复制，不相对导入仓库文件；声明已有 pydantic-core 依赖，不安装任何包。

新版定向验收：`.venv/bin/python checks/similarity_flow.py`（0/0.5/1、双报告、失败无部分成功），`.venv/bin/python checks/similarity_onboarding.py`（两个本地协议替身和全新后端 HTTP 链路）。替身报告不是 M2。
