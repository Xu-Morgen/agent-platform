# 本地 embedding 模型制品

`bge-small-zh-v1.5.json` 是本次真实验证的导入清单。将其复制为模型目录中的 `embedding.json`，同目录按清单路径放置三个文件，再通过平台设置导入。仓库不分发模型权重；导入和任务运行不会联网下载或自动安装依赖。

来源：[BAAI 原始模型](https://huggingface.co/BAAI/bge-small-zh-v1.5)，[Xenova ONNX 转换](https://huggingface.co/Xenova/bge-small-zh-v1.5/tree/75c43b069aac4d136ba6bc1122f995fedcfd2781)。实际使用后者固定修订的 `onnx/model.onnx`、`tokenizer.json`、`config.json`，MIT 许可证，SHA-256 见清单。不声称此 ONNX 文件由 BAAI 发布。

运行环境：Linux x86-64、Python 3.12、ONNX Runtime 1.22.1、ONNX 1.18.0、tokenizers 0.21.4、NumPy 2.2.6；项目依赖由 `uv.lock` 固定。CPU float32，CLS 池化后 L2 归一化，查询指令随清单固定。仅接纳内嵌权重的 BERT 三个 int64 输入、三维 float32 token 输出，不执行自定义算子或模型 Python。

首版默认批次 8、推理线程 2、同时一个任务模型进程。单任务可缓存 2000 个不同片段；请求最多 500 片段、一百万字符、topK 最多 100。进程虚拟地址空间上限 3 GiB，容量等待及单次工作进程请求各最多 120 秒。排队时不加载模型，任务结束释放进程。超限明确失败，不裁减资料后伪装成功。

实测（2026-09-22，本机 i7-14700 虚拟化环境、Python 3.12.3）：冷加载 0.55～0.61 秒，双句诊断约 5.4 ms；1×30 字符约 5.1 ms、8×100 字符约 80 ms、8×510 字符（含特殊 token 为 4096 token）约 515 ms；峰值 RSS 约 407 MiB。只是此次轻量测量，不是性能承诺。1200 个汉字加英文文本切分后可无遗漏拼回原文，每段完整编码通过；超长查询/片段报错。详细质量与生命周期验证随实施计划记录。
