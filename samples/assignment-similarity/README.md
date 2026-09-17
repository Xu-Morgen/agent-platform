# 最小查重产品

平台核心不包含查重分支。`flows/similarity.json` 组织清洗 → 计分 → 语义输入适配 → 模型语义分析 → 双报告组装。服务保存时由平台编译实例；调用方式见 [接入操作](../README.md)。

## 源码与分发

| 路径 | 职责 |
| --- | --- |
| `source/contracts.py` | 输入、定量、定性及完整报告的权威契约 |
| `source/preprocessing.py` | 文本规范化与清洗后非空检查 |
| `source/scoring.py` | paragraph-exact-v1 确定性计分 |
| `blocks/*.py` | 从权威源生成的独立单文件分发块 |
| `packages/semantic/` | 一次模型交互的语义分析包 |
| `flows/similarity.json` | 业务拼图配方 |

修改权威源后，在根目录运行：

```bash
.venv/bin/python samples/assignment-similarity/sync_contracts.py
.venv/bin/python samples/assignment-similarity/generate_blocks.py
```

两者均支持 `--check` 检查生成内容的一致性。生成文件是运行时分发资源，不能作为“重复测试代码”删除；不直接编辑分发副本。同一会话内修改内容后须更新模块版本再加载，已有实例仍使用固定快照。

旧 `instance.json`、`entry.py`、`workflow.py` 和旧图状态模型已移除。`source/` 仅用于维护算法和生成模块，不是另一套服务入口。

## 输入、算法与输出

输入为 `targetText` 和非空 `comparisonTexts` 数组，均为纯文本。清洗统一 NFC、换行与水平空白，去除空行；清洗后任一文本为空即失败。

每个目标段落仅与对照文本的完整段落精确比较。相似度为匹配目标段落字符数 / 目标总字符数；按 Unicode 码点计数，不计段落间换行。目标重复段落按出现位置分别计数；对照重复段落不重复增加分值。算法不做模糊匹配或语义改写。

教学例：目标“甲乙\n丙丁”，对照“甲乙”，比例为 0.5。实际业务输入由调用者提供；不附带原验收数据与人工模拟报告。

输出包含 quantitative 和 qualitative。模型说明仅提供风险与建议，不输出最终是否抄袭的布尔判定。报告组装检查全部对照项覆盖；模型失败或输出不合法时整个任务失败，不发布部分成功报告。

## 拼图接线

| 节点 | 输入来源 |
| --- | --- |
| clean | 完整服务输入 |
| score | clean 完整输出 |
| adapt | clean 完整输出 |
| semantic | adapt 完整输出 |
| assemble.request | 原服务输入 |
| assemble.quantitative | score 完整输出 |
| assemble.qualitative | semantic 完整输出 |
| 服务出口 | assemble 完整输出 |

语义节点绑定已保存环境的 `model` 连接，默认 maxOutputTokens=4096、loopLimit=1、tokenLimit=32768；全局预算也为 loop=1、token=32768。当前适配器需显式选择非严格模式，按实际部署调整预算和超时。

2026-09-17 用户确认当前产品验证完成。本轮仅验证精简后的本地执行与契约，没有重新调用真实模型或生成新的真实模型验收报告。
