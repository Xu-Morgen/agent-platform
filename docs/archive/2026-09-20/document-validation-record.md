# 文档读取与出题本地验收记录

此处保留清理前的历史验证记录，不代表线上模型或人工质量验收通过。当前使用见[实例说明](../../../examples/document-question-generation/README.md)。

一次性验收脚本已从当前目录删除，不再提供下列历史命令作为当前操作入口。原脚本可在 Git 提交 `6fb84d3` 查看：`scripts/verify_document_runtime.py`、`examples/document-question-generation/verify.py`、`examples/document-question-generation/make_fixtures.py`。后续按用户要求，`tests/` 下的回归测试也已全部删除；历史文件同样可从上述提交查看。下文保留当时的记录与命令，不作为当前操作指引。

## 平台文件与运行环境历史验证


已做不下载依赖的静态声明、文件格式/超限/摘要/归属/重启恢复、模型缓存损坏与离线复用、真实子进程自定义校验、CPU 取消及 API 桥接测试，以及原有数据流、重试与持久化回归。模型网络失败测试使用本地 HTTP transport 替身，不等同真实 OCR 验收。

已在用户授权后完成新环境实际安装、3 个官方模型下载与真实扫描 PDF OCR；结果为 `PLATFORM OCR TEST 2026`，删除原文件后执行及禁用下载连接后的离线重复执行均成功。最终验收环境标识为 `d82ce67311506ab1492e564f14277227e509db6b4378e344fb7b8012162b7c6d`。原生系统对话框未人工走查，控件逻辑已自动验证保存/替换/移除/取消和迟到响应隔离。

真实 OCR 验收脚本已准备为 `scripts/verify_document_runtime.py`，需显式执行：

```bash
.venv/bin/python scripts/verify_document_runtime.py --cache-dir /tmp/agent-platform-ocr-runtime
```

脚本已实际执行通过。重新运行会安装或复用 `rapidocr-onnxruntime==1.4.4`、`onnxruntime==1.23.2`、`PyMuPDF==1.26.7` 及锁定的传递依赖，下载 3 个带官方 SHA-256 的 PP-OCRv4 模型。版本存在性已核对 PyPI，模型来源为 [RapidAI 官方模型清单](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)。脚本构造合成扫描 PDF，经过任务文件保存、源文件删除、实际任务调用与离线复用；禁止把尚未执行的脚本当作通过记录。安装前须遵守工作区确认约定。

对于改造前未记录依赖锁的持久资源，首次成功恢复会补全当前经过验证的环境锁；原实例内容摘要、版本、任务历史保持原身份，之后继续使用固定锁。平台无法追溯从未记录过的历史安装状态。已使用改造前源码实际创建持久记录，并验证新版恢复、任务执行和第二次恢复通过。

自动验证记录：文件/声明/进程/缓存边界 12 项、重试与预算 9 项、完整数据流 8 项、持久化 5 项；Node 输入与文件控件 8 项。另执行真实 pip 离线冲突检查，得到 DEPENDENCY_CONFLICT；无匹配 wheel 得到 DEPENDENCY_WHEEL_UNAVAILABLE。未执行打包、发布或系统配置修改。

## 文档出题历史验证


准备好的环境在本次工作中使用 `/tmp/agent-platform-ocr-runtime`；它是临时验证缓存，正式桌面会使用自己的持久目录。运行下面的脚本可能准备/修复此独立缓存，但不调用线上模型：

```bash
.venv/bin/python examples/document-question-generation/verify.py \
  --cache-dir /tmp/agent-platform-ocr-runtime
.venv/bin/python -m unittest discover -s tests -p test_document_question_generation.py -v
```

第二个命令在主环境中只运行契约/协议检查，缺少 DOCX/PDF 依赖时会明确跳过解析检查。解析检查需在已准备环境中运行，不应把 skip 当作验收通过。

验收材料全部由 make_fixtures.py 自制。verify.py 通过真实平台子进程、上传文件副本和真实本地 OCR 处理 DOCX、文字/三页扫描/混合 PDF；出题响应由离线桩提供，第一次故意返回少题，第二次合法，检查仅包重试、读取一次、末页资料完整进入两次请求、预算累计，以及空白/损坏文档不会进入出题步骤。另验证资料不足只调用一次且记账、扫描第一页后取消实际工作进程。

本次验证结果：独立环境中的 9 项契约/解析/协议检查、9 项流程重试检查、12 项平台文件/依赖/取消回归和 4 项桌面文件控件检查通过；samples 两个块、两个包及独立契约的三个入口均成功加载。DOCX 合并单元格去重与嵌套表格位置也已检查。读取块的文件大小、渲染尺寸上限有直接边界检查；OCR 无结果/低置信度使用故障注入验证，确认后页失败不会返回前页正文为成功结果。

真实线上模型、答案正确性、单选唯一性，以及复杂排版/低清晰度资料的人工质量验收未完成，按用户要求暂缓。后续使用自制或授权文档实际出题，逐项核对题目依据与答案；JSON 合法不能代替业务验收。
