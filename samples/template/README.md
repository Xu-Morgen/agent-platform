# 三类资源与拼图模板

复制整个目录后修改包清单 `packageId`、块装饰器 `id` 和配方名称。包、块与契约由平台加载，完整实例由拼图生成。详细开发步骤见 [指导手册](../../docs/resource-guide.md)。

| 资源 | 加载类型及路径 | 说明 |
| --- | --- | --- |
| 通用块 | `block`，`blocks/text.py`、`rename.py`、`condition.py`、`lms.py` | 一个文件一个入口；不绑定模型环境 |
| 业务包 | `package`，`packages/example` | 一次模型交互；逐节点配置 instruction、maxOutputTokens 和预算 |
| 独立契约 | `contract`，`flows/contracts.py`，symbol=`Message` | 服务输入输出契约；非空 text 字段 |

在仓库根目录导入草稿（使用同一后端会话）：

```bash
.venv/bin/python samples/flow_templates.py samples/template sequence --platform-url http://127.0.0.1:8000
```

| 配方 | 页面配置要点 | 预期行为 |
| --- | --- | --- |
| `sequence` | 独立 Message 契约作为服务输入输出；两个文本块前后连接 | `{"text":"你好"}` 原样返回，无模型调用 |
| `branch` | 条件块输出 bool；两个分支分别声明共同类型的出口 | text 为 continue 走 then，否则走 else；均返回原文本 |
| `repeat` | 初始携带值接服务输入，更新值接循环体输出 | 执行两次透传；改为 0 次则输出初始值 |
| `while` | 携带值接条件与循环体，显式填写最大次数 | 普通文本立即退出；continue 一直不变则到上限失败 |
| `two-packages` | 同包两次，各自绑定 model 连接、独立参数和预算 | 第一节点概括，第二节点根据前序输出给出建议 |

双包配方追加 `--environment-id 实际环境ID --non-strict`。全局 loop 至少 2；每节点至少 1。具体预算以 JSON 中的配置为准。导入后在桌面点击“检查健康状态”，选择草稿，检查并保存实例，再到任务页提交。

`flows/*.json` 是资源配方；`${资源.字段}` 由脚本替换为目录返回的实际标识。不能直接把含占位符的配方当作 FlowDraft 提交。`flows/contracts.py` 是包业务契约权威源，`sync_contracts.py` 同步到可独立加载的包；`--check` 仅检查分发文件是否漂移。单文件块自包含，同结构是否可连接由端口检查决定。

保留的短输入用于说明模板操作，不是验收数据集。测试替身、测试脚本和批量测试数据已移除。
