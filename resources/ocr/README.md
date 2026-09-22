# 本地 OCR 模型制品

平台使用完整 ONNX 模型组合，通过设置页导入及选择；操作和接口见 [OCR 手册](../../docs/local-ocr.md)。模型权重属于应用运行资产，不提交仓库。

首版清单：[pp-ocrv4-mobile.json](pp-ocrv4-mobile.json)。准备目录时将其复制为 `ocr.json`，另放置 `det.onnx`、`rec.onnx`、`cls.onnx`，摘要必须与清单一致。清单记录完整适配器、来源、许可证与运行依赖，不能用其他模型文件冒充。

| 文件 | 来源 |
| --- | --- |
| det.onnx | [PP-OCRv4 中文 mobile 检测](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/det/ch_PP-OCRv4_det_mobile.onnx) |
| rec.onnx | [PP-OCRv4 中文 mobile 识别](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/rec/ch_PP-OCRv4_rec_mobile.onnx) |
| cls.onnx | [mobile 方向分类](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx) |

已有旧 OCR 资源缓存时，可复制 `storage/runtimes/models/<sha256>/<filename>` 中对应的三个文件，无需重新下载。平台导入后自行保存不可变副本，不引用这个准备目录。

识别字典来自识别 ONNX 的 `character` metadata，不加载模型目录中的代码。首版固定 RapidOCR 1.4.4 适配行为和平台 ONNX Runtime 1.22.1；原旧块使用 1.23.2 的独立环境继续保留。平台依赖通过项目 `uv.lock` 管理，不由清单安装。合成识别检查不代表所有模型或文档质量通过。
