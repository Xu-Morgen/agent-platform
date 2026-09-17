# 产品接入与指导样例

三类资源分别是单文件通用块、业务包、独立契约。契约用于约束端口，不是可执行节点；顺序、条件和循环是组合这些资源的控制结构。完整开发规则与逐步操作见 [指导手册](../docs/resource-guide.md)。

## 不依赖模型的起步样例

先启动后端，再在另一个终端导入顺序配方：

```bash
.venv/bin/python -m agent_platform --port 8000
```

```bash
.venv/bin/python samples/flow_templates.py samples/template sequence --platform-url http://127.0.0.1:8000
```

此命令加载独立契约与文本块，并创建草稿。若使用桌面后端，把 URL 换成页面顶部的实际地址；点击“检查健康状态”刷新资源与草稿，选择“纯块顺序”，检查接线并保存实例。在任务页输入 `{"text":"你好"}`，结果为相同对象。

## 三类指导样例

| 类型 | 可复制文件 | 用途 |
| --- | --- | --- |
| 单文件通用块 | [文本透传](template/blocks/text.py)、[字段转换](template/blocks/rename.py)、[条件](template/blocks/condition.py)、[LMS 解包](template/blocks/lms.py) | 确定性处理、显式转换、严格布尔条件 |
| 业务包 | [标准模型交互包](template/packages/example/package.json) | Prompt、参数、模型能力声明与输出契约 |
| 独立契约 | [Message](template/flows/contracts.py) | 加载时填写 symbol `Message`，作为服务或容器端口 |

[标准模板说明](template/README.md)提供顺序、分支、repeat、while、同包双节点的完整配方；[查重产品说明](assignment-similarity/README.md)展示组合成业务产品的方式。

## 调用查重产品

自行准备业务输入 JSON 文件，结构为 `{"targetText":"目标文本", "comparisonTexts":["对照文本"]}`。仓库不再附带验收数据集或人工模拟报告。下面的路径、地址和模型名须替换成实际值：

```bash
read -rsp 'API Key: ' MODEL_API_KEY
export MODEL_API_KEY
printf '\n'
.venv/bin/python samples/invoke_similarity.py \
  --platform-url http://127.0.0.1:8000 \
  --adapter openai-chat \
  --model-url https://YOUR_PROVIDER/v1 \
  --model YOUR_MODEL_NAME \
  --credential-env MODEL_API_KEY \
  --non-strict \
  --input /absolute/path/business-input.json \
  --output /absolute/path/report.json
unset MODEL_API_KEY
```

脚本创建环境、加载模块、保存拼图实例、提交输入、等待终态并导出结果；真实模型调用可能产生费用。`--input` 必填。也可只创建查重草稿，在服务页检查后保存：

```bash
.venv/bin/python samples/flow_templates.py samples/assignment-similarity similarity --platform-url http://127.0.0.1:8000 --environment-id 实际环境ID --non-strict
```

模型连接的 connectionId 为 `model`。当前 OpenAI 兼容及 Ollama 适配器均不保证完整输入 token 上界，须显式选择非严格模式；仍记录用量并执行超额检查，缺失有效 usage 会失败。兼容服务可指定 `--output-token-parameter max_tokens` 或 `--no-json-mode`。Ollama 使用 `--adapter ollama-chat` 和服务根地址。协议细节见 [模型说明](../docs/protocols/model.md)。

所有加载路径由后端读取，推荐绝对路径。脚本和后端须共享文件系统。导出报告不包含环境地址和凭据，但报告文本可能引用原输入。重启会清空服务、凭据、任务与历史，须重新加载配置。
