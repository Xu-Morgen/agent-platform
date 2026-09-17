# I5 查重交付与真实验收状态

- 日期：2026-09-17。
- 状态：I5-T01～T07 已完成；I5-T08 阻塞，M2 未完成。
- 已交付：严格契约、固定文本清洗、确定性段落计分、单次语义包、完整 LangGraph、可复制模板和接入操作。
- 已完成的模型链路检查使用实际 Ollama 适配器连接本地 HTTP 协议替身，不是真实模型报告。平台源码无需改动。

## 已执行的定向验证

在仓库根目录用 `.venv/bin/python` 执行下列文件，均通过：

| 文件 | 结果 |
| --- | --- |
| `checks/similarity_contracts.py` | 正常报告通过；严格类型、数值范围、重复/越界/缺失索引拒绝；双方同时漏掉尾项也拒绝 |
| `checks/similarity_preprocessing.py` | NFC、CRLF/CR、水平空白和空段；保留大小写、标点及段内非水平分隔符；空白错误返回原字段路径 |
| `checks/similarity_scoring.py --artifact-dir artifact` | 1/0/0.5、目标重复按位置、对照重复不放大；7 篇 DOCX 本地 1 对 6 和自比较通过 |
| `checks/similarity_semantic.py` | 一次模型尝试计一轮；缺项、重复、错误类型和额外布尔判定失败；本地 HTTP 替身 |
| `checks/similarity_workflow.py` | 四节点双报告；模型错误不发布定量部分；严格不支持及空白输入零请求；本地 HTTP 替身 |
| `checks/template_copy.py` | 临时目录复制两包、改标识；两配置输出限额分别为 11/17；全局两轮、局部各一轮；本地 HTTP 替身 |
| `checks/similarity_onboarding.py` | 全新后端经真实 HTTP 加载和执行；关闭后重启旧任务 404、服务清空；模型为本地 HTTP 替身 |
| `checks/similarity_acceptance_input.py` | 真实验收用合成 1 对 6 输入合法，字符规模和确定性计算通过；未调用模型 |

两个产品的 `sync_contracts.py --check` 均通过。各完成卡片均已独立提交，另有一次水平空白边界修复。未安装依赖、未打包、未执行全量测试。

## artifact 使用情况

仅通过 Python 标准库读取 DOCX 的 Word 正文，未改动或提交 artifact。按路径排序的 7 篇正文原始长度为 1681、1514、883、1395、1492、1463、2090 字符；第一篇对其余六篇的完全段落匹配比例为 0.0012338062924120913、0、0、0.0012338062924120913、0、0.0012338062924120913。第一篇自比较为 1。

这些数值只验证段落精确匹配，不代表 AIGC 检测或抄袭准确率。PDF 和 XLSX 未解析，未把原文发送至真实外部模型或写入交付记录。

## T08 阻塞与继续条件

实际环境检查：`curl -sS --max-time 3 http://127.0.0.1:11434/api/tags` 返回连接失败（退出码 7）；本机没有 `ollama` 命令，未发现模型地址/模型名相关环境变量，也未获得其他模型地址和名称。未安装服务、未下载模型、未发起猜测性的远程调用。

需要一个可用的 Ollama Chat 地址及已部署模型名；若有认证，还需本机凭据环境变量。当前适配器不保证严格总 token 上界，因此真实验收需显式 `--non-strict` 并记录 usage 的实际 quality/source，不可宣称严格模式已验收。

已准备 [合成 1 对 6 输入](../../samples/assignment-similarity/examples/acceptance-1v6.json)，每篇不含换行的 Unicode 码点数为 1559、1559、1559、1561、1569、1578、1559。内容是虚构校园共享阅读项目及其变体，不包含学生身份。确定性分值依次为 1、0.7485567671584349、0.24246311738293777、0.1629249518922386、0.5060936497754971、0。变体用于结构和计分检查，不预设模型应作出的语义判断。

获取实际环境后，按 [接入说明](../../samples/README.md) 启动后端，再执行：

```bash
.venv/bin/python samples/invoke_similarity.py \
  --model-url ACTUAL_OLLAMA_URL \
  --model ACTUAL_MODEL_NAME \
  --non-strict \
  --input samples/assignment-similarity/examples/acceptance-1v6.json \
  --output /tmp/i5-real-report.json
```

需要认证时补充 `--credential-env 环境变量名`。该命令通过平台 HTTP→固定快照→LangGraph→语义包→实际适配器执行。只有返回 completed、同时包含两类报告且全局/局部各一轮，才能保存审阅脱敏后的报告、实际模式和用量证据，再将 T08 及 M2 标记完成。失败时保留错误，不自动重试或代填定性结果。

当前没有真实模型双报告和用量记录，不能用替身的 token=48 替代。待真实验收后更新本节、任务卡、迭代索引和项目状态。
