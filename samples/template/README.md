# 模块与拼图标准模板

`packages/example/` 是一次模型交互包，`blocks/` 是独立 Python 通用块，`flows/` 是可复制的顺序、if/else、repeat、while 和同包双节点拼图。已移除旧 `instance/` 手写入口，实例由平台编译生成。

1. 复制整个 `samples/template`，修改包清单 `packageId`、块装饰器 `id` 和拼图名称。包里不填写地址、密钥或环境 ID。
2. 服务页选择“单文件通用块”加载 `blocks/text.py` 和 `blocks/condition.py`；选择“业务包目录”加载 `packages/example`。独立契约可选择“契约文件”、路径 `blocks/text.py`、symbol `Message`。
3. 纯块顺序：服务输入选文本透传输入，插入两个文本透传；第一节点接服务输入，第二接第一输出，服务出口接第二输出。不配置模型或预算。输入样例填写 `{"text":"合成输入"}`。
4. 条件：先插入继续条件并接服务输入，插入 if，条件选该块完整输出；共同出口选文本透传输出，两个分支分别插入文本透传，分支出口接各自节点输出。
5. 固定循环：repeat 次数可填 0 或 2，携带契约选文本透传输入；初始值接服务输入，循环体文本透传接本循环携带值，下轮值接体内节点输出。while 另选继续条件块并把携带值接其输入，显式填写最大次数；普通合成输入首次条件为假，输入 continue 且一直不改变时会到上限报错。
6. 双包：插入同包两次，第二输入接第一输出；逐节点打开配置窗，instruction 分别为“概括输入内容。”和“对前序结果给出建议。”，maxOutputTokens 分别为 128、256。两者分别选择已保存环境的 model 连接。当前适配器需显式关闭严格模式，全局 loop 至少 2。
7. 保存草稿不会创建服务。校验并保存实例后，在任务页选稳定服务、填入输入样例并提交。

也可将 JSON 资源配方导入为会话草稿，随后在同一后端会话的服务页检查并保存：

```bash
.venv/bin/python samples/flow_templates.py samples/template sequence --platform-url http://127.0.0.1:8000
# 另有 branch、repeat、while；two-packages 额外传 --environment-id 实际环境ID --non-strict
```

桌面独立启动时，把地址改为页面顶部显示的后端地址。`flows/*.json` 的 `${资源.字段}` 由加载器替换为实际内容摘要资源 ID；不是可直接提交的 FlowDraft，也不写死环境 ID。点击桌面“检查健康状态”刷新目录和草稿。

包业务契约仍由 `flows/contracts.py` 权威源生成，`sync_contracts.py --check` 检查分发副本；旧入口不参与新版编译。块是可独立加载的声明；同结构类型由平台端口检查。后续复杂业务应将共享契约生成到各独立模块，避免运行时相对文件依赖。

定向检查：`.venv/bin/python checks/template_copy.py`（临时复制改标识、纯块控制流和双节点配置/调用）；模型部分明确使用本地 HTTP 协议替身，不是 M2。页面闭环见 I8-T08。
