# I8 真实查重验收准备与阻塞

> 历史交接记录：本页记录当时的实现及验证，不是当前使用入口。2026-09-17 用户已确认最小产品验证完成；精简后旧测试命令、数据和入口已移除。当前状态见 [迭代索引](../iteration-plan.md)，操作见 [项目入口](../../readme.md)。

日期：2026-09-17。I8-T09 状态：阻塞；新版 M2 未完成。I8-T07 的拼图迁移和 I8-T08 的新版 M1 已完成。

阻塞条件：本次会话未提供真实模型 Base URL、模型名或凭据来源。只检查了常见环境变量是否设置，未打印任何值：MODEL_API_KEY、OPENAI_API_KEY、DEEPSEEK_API_KEY、MODEL_BASE_URL、OPENAI_BASE_URL、MODEL_NAME、OLLAMA_HOST 均未设置。已向用户询问可用端点、模型及安全凭据来源，尚未收到。没有以其他服务或替身冒充真实模型。

已完成准备（不是 M2）：

- `.venv/bin/python checks/similarity_acceptance_input.py`：合成目标/六份对照清洗后字符数为 1559、1559、1559、1561、1569、1578、1559，规模符合约 1500 字 1 对 6。
- `.venv/bin/python checks/similarity_onboarding.py --input samples/assignment-similarity/examples/acceptance-1v6.json`：新版 FlowDraft、OpenAI/Ollama 两个本地 HTTP 协议替身均 completed，定量/定性各 6 项，局部 semantic loop=1、全局 loop=1，记录 usage、instanceId、版本及非严格模式；退出重启清空。协议替身的用量与定性内容均为合成，不作为真实证据。
- `samples/invoke_similarity.py` 已使用单文件块与新拼图生成实例，导出结果不含输入、环境地址、凭据或环境快照；模型生成内容分享前仍需人工审阅脱敏。

解除阻塞后，在本机安全配置凭据环境变量，启动后端并运行（替换实际端点和模型）：

```bash
.venv/bin/python samples/invoke_similarity.py \
  --platform-url http://127.0.0.1:8000 \
  --adapter openai-chat \
  --model-url 服务商API根地址 \
  --model 实际模型名 \
  --credential-env MODEL_API_KEY \
  --non-strict \
  --input samples/assignment-similarity/examples/acceptance-1v6.json \
  --output /tmp/i8-real-similarity.json
```

如服务商要求，显式选择 `--output-token-parameter max_tokens`；地址与模型能力以实际部署为准。不得把 API Key 放进参数值或仓库。

完成门槛：真实适配器 completed，quantitative/qualitative 各覆盖六份对照，记录实际模型、适配器、模式、固定实例与版本、全局及局部 loop/token usage；审阅报告脱敏后回填任务卡和索引。失败则保留具体原因，不标记完成。此检查不评价模型语义准确率。
