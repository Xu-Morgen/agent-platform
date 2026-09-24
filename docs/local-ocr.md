# 本地 OCR 模型与受控识别

核对日期：2026-09-24。

平台管理完整 OCR 模型组合；普通块负责 PDF 渲染、识别时机、阅读顺序、置信度处理和正文定位。当前支持 Linux x86-64 / Python 3.12、RapidOCR 1.4.4 的 ONNX CPU 组合，不增加资源类别或改变 flow-6。

## 导入与更换

1. 按 [模型制品说明](../resources/ocr/README.md) 准备包含 `ocr.json`、检测/识别/方向分类 ONNX 的目录。
2. 在「平台设置 → 本地 OCR 模型组合」选择目录并点击「检查并导入」。平台校验摘要、复制文件并实际识别合成小样例；成功后显示就绪。导入不联网下载、不执行目录中的 Python、不安装清单依赖。
3. 选择模型并保存默认选择。更换只影响后续提交，不修改已提交任务或服务版本。任务提交固定完整模型身份，包含文件摘要、字典来源、适配器版本和依赖。
4. 「验证所选模型」重新检查文件并运行小样例，显示识别文字、加载/推理耗时和进程峰值内存。可运行不等于复杂版面质量通过。

模型身份由规范化完整清单计算，文件存于 `storage/ocr-models/`，元数据及默认选择保存在 PostgreSQL。同一身份不可覆盖；移动导入源不影响应用副本。恢复时核对摘要；损坏明确标记不可用，不回退块内模型或其他引擎。已标记 unavailable 的模型即使恢复文件，也须重新执行“验证所选模型”，成功后才恢复 ready；同身份重新导入只检查现有副本，不覆盖损坏文件。备份须包含完整 storage。`--memory` 使用会话临时副本。

含 `ocr=True` 块的服务在提交时要求就绪默认模型，包括子服务、条件及未执行分支；即使本次只读 DOCX 或纯文字 PDF，也固定 OCR 模型。实际不需要 OCR 的页面不会进行推理或产生 OCR 调用记录。

## 资源升级

- 上传文档块：`examples/document-question-generation/read_document.py`，`read-document@5.0.0`。
- 知识库读取块：`resources/rag/blocks/read_docx.py`，`rag-read-docx@3.0.0`。

两者只声明文档解析依赖，不再声明 det/rec/cls 下载地址或直接初始化 RapidOCR；通过平台异步识别页面，保留原有 0.5 置信度、空白框过滤和失败规则。知识库 OCR 页面定位加入实际模型身份，因此换模型不会复用相同的 OCR 片段标识。

通过服务页导入新版块，替换节点并重新保存实例；如果父服务固定了子服务，还须显式更新该固定引用。历史资源、任务和固定实例不自动改写，旧版块继续采用其锁定运行环境和旧模型依赖。

## 块接口与严格契约

权威来源：[contracts/ocr.py](../src/agent_platform/contracts/ocr.py)。模型清单固定检测、识别与分类三个互异文件的路径和 SHA-256；识别字典必须内嵌 ONNX metadata，当前不接收外置字典或任意引擎配置。适配器固定 CPU、预处理与后处理方式；不同引擎需要相应适配实现，不能仅替换文件扩展名。

```python
# 在 @block(...) 中声明 ocr=True，入口为 async 并声明 context: BlockContext。
import base64
from agent_platform.contracts.ocr import OCRRequest

# png_bytes 来自块按业务规则渲染的页面。
result = await context.ocr(OCRRequest(
    image_base64=base64.b64encode(png_bytes).decode(),
    use_classification=False,
))
# result.lines: points（四个 x/y 点）、text、confidence。
# result: model_id、image_sha256、width/height、queue_seconds/inference_seconds。
```

只接受单帧 RGB PNG：原始图片最多 9 MiB，单边最多 6000，最多 2000 万像素。不接收本机路径或模型选择参数。平台校验能力声明、任务状态、严格请求、固定模型及返回图片摘要，返回框坐标和置信度必须有限且在范围内。受信任块负责图片与原文来源关系，平台不宣称证明渲染忠实性。

空白图片可正常返回零行；是否允许空结果或低置信度由业务块决定。PDF 读取块禁用行方向分类，保留 PDF 渲染方向。错误包括 `OCR_NOT_SELECTED`、`OCR_NOT_READY`、`OCR_INCOMPATIBLE`、`OCR_INPUT_LIMIT`、`OCR_INFERENCE_ERROR`、`OCR_CAPACITY_EXCEEDED`，不按输出契约错误自动重试。

## 生命周期和记录

OCR 使用独立容量池，同时一个模型进程；每次识别完成即释放进程和容量，不跨页面缓存引擎。这样不会在后续 embedding 或其他节点执行期间占用 OCR 容量，避免并发任务以相反顺序使用两种能力时交叉等待。代价是每页重新加载模型，推理耗时不包含加载耗时。等待容量和每次工作进程通信最多 120 秒；工作进程地址空间上限 3 GiB，推理线程 1。单任务最多 200 次 OCR 调用；单次最多 5000 行、20 万字符。图片不缓存、不写入 OCR 历史；任务原件仍按文件/知识库规则保存。

任务历史保存完整模型快照，以及调用节点、块源码摘要、图片摘要、尺寸、方向分类选项、文字框、置信度和耗时。调用错误保留在步骤与任务错误中。主动取消或应用退出终止本地推理并释放进程；这与远端 LLM 主动取消时等待传输结束不同。本地 OCR 不消耗 Prompt loop 或远端计费 token，不提供断点续跑。

管理接口前缀 `/api/v1/ocr`：`GET /models`、`GET/PUT /selection`、`POST /import`（`{directory}`）、`POST /models/{modelId}/check`、`GET /jobs/{jobId}`。导入与诊断返回 202 操作记录，同一时间仅允许一项管理操作；仅保留本会话最近 20 项。管理 API 不开放匿名识别接口，识别只在任务上下文内进行。

当前无自动下载、物理删除、GPU、任意 OCR 引擎或复杂版面分析；不保证复杂表格、多栏、倒置、倾斜或低清晰度材料的识别完整性。实际验证及限制见 [验收记录](archive/2026-09-22/local-ocr-validation.md)。
