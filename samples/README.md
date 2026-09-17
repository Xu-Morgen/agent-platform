# 通用块创建、业务包接入与查重操作

从仓库根目录运行下列命令，使用已有 `.venv` 依赖。平台、包和实例都是受信任的本地 Python 源码，非沙箱；本例不需要安装新依赖。独立后端与桌面后端是不同会话，不共享内存。

## 创建单文件通用功能块

一个通用功能块最少只需要一个 `.py` 文件，在已有平台依赖的运行环境中加载。文件内包含输入输出契约、块声明和一个确定性业务函数，适合文本清洗、字段转换、计分或布尔判断。

### 最小目录与代码

例如自行创建以下文件（下面的 `my-blocks/trim_text.py` 是创建示例，仓库未预置）：

```text
samples/
└── my-blocks/
    └── trim_text.py
```

`trim_text.py` 的完整内容：

```python
from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel


# 1. 输入输出契约：严格检查字段类型，拒绝未知字段。
class Input(StrictModel):
    text: str


class Output(StrictModel):
    text: str


# 2. 块声明：标识、版本、名称及用途。
@block(
    id="trim-text",
    version="1.0.0",
    name="去除首尾空白",
    description="移除文本两端的空白字符",
)
# 3. 业务函数：明确接收 Input 并返回 Output。
def run(value: Input) -> Output:
    return Output(text=value.text.strip())
```

执行时的数据流：

```text
输入 JSON → 平台校验 Input → run() → 平台校验 Output → 后续节点或服务出口
```

输入 `{"text":"  你好  "}`，输出 `{"text":"你好"}`。这里允许输出空字符串；如业务要求非空，应在契约中明确声明并处理清洗后为空的情况。

### 当前加载要求

- 文件中恰好一个被 `@block` 注册的业务函数。函数只有一个无默认值的参数，参数和返回值都必须有类型注解。
- `id` 以字母开头，后续可使用字母、数字、下划线和连字符；`version` 使用如 `1.0.0` 的版本号，`name` 必填，`description` 用于说明用途。
- 对象契约继承 `StrictModel`，嵌套对象也遵循同样要求。简单输入输出可直接声明为 `str`、`int`、`bool` 等支持的 JSON 类型，不必创建模型类。
- 自有契约和逻辑放在同一文件中，不相对导入旁边的源码。可使用 Python 标准库及平台已提供的依赖；其他第三方库需在装饰器的 `dependencies` 中声明版本范围，并提前安装到后端运行环境，加载器不会自动安装。
- 加载时会导入文件并检查声明，不调用业务函数；不要在模块顶层执行实际业务操作。
- 同一会话内，同一个 `id` 和 `version` 不接受不同文件内容；修改已加载块后，应更新版本号再加载。

通用块不需要 `package.json`、`instance.json`、模型环境或模型预算。`flows/*.json` 用于描述多个节点组成的流程；查重样例中的 `generate_blocks.py` 用于生成独立分发块，普通块可以直接手写，无需生成器。

### 在页面加载并调用

1. 服务页“资源类型”选择“单文件通用块”，“本地路径”填写刚创建的 `.py` 文件路径，symbol 留空。例如当前工作区为 `/home/nemo/agent-platform/samples/my-blocks/trim_text.py`；项目位置不同则替换前缀。
2. 点击“加载资源”，填写服务名称；输入契约选择“去除首尾空白 · 输入”，输出契约选择“去除首尾空白 · 输出”。
3. 插入“去除首尾空白”节点，添加接线：目标选完整输入，来源选服务输入完整值。
4. 在服务出口添加接线：目标选完整输入，来源选该节点的完整输出。
5. 输入样例填写 `{"text":"  你好  "}`，点击“校验并保存实例版本”。未完成时也可先保存草稿。
6. 到任务页选择刚保存的服务，填入样例并提交，结果应为 `{"text":"你好"}`。

无需创建文件即可尝试的现成样例：

| 块 | 相对项目根目录的加载路径 | 输入与输出 |
| --- | --- | --- |
| [文本透传](template/blocks/text.py) | `samples/template/blocks/text.py` | `{"text":"你好"}` → `{"text":"你好"}` |
| [字段转换](../examples/flows/blocks/rename.py) | `examples/flows/blocks/rename.py` | `{"legacyText":"你好"}` → `{"text":"你好"}` |
| [非空判断](../examples/flows/blocks/condition.py) | `examples/flows/blocks/condition.py` | `{"text":"你好"}` → `true` |

本地路径由后端读取，建议填写绝对路径；相对路径按后端工作目录解析。业务包则选择“业务包目录”并填写包含 `package.json` 的文件夹，如 `samples/template/packages/example`。

## 无真实模型的接入演示

```bash
.venv/bin/python checks/similarity_onboarding.py
```

脚本启动全新后端进程和本地 HTTP 模型协议替身（分别验证 OpenAI 兼容与 Ollama），通过与下方相同的接入脚本创建环境、加载包与单文件块、解析拼图、保存、提交并查询双报告，再关闭后端并验证重启后原任务 404。替身只验证接线和契约，不代表 M2 真实模型验收。

## 使用远程 OpenAI 兼容模型 API

1. 在终端 A 启动后端：

   ```bash
   .venv/bin/python -m agent_platform --port 8000
   ```

2. 在终端 B 调用接入样例，把地址和模型名替换为服务商提供的实际值，并预先设置 MODEL_API_KEY 环境变量：

   ```bash
   .venv/bin/python samples/invoke_similarity.py \
     --adapter openai-chat \
     --model-url https://api.openai.com/v1 \
     --model YOUR_MODEL_NAME \
     --credential-env MODEL_API_KEY \
     --non-strict \
     --input samples/assignment-similarity/examples/input.json \
     --output /tmp/similarity-report.json
   ```

   后端地址可用 `--platform-url` 指定。模型需要认证时，预先在本机环境中设置凭据，再使用 `--credential-env 环境变量名`；不把密钥写入示例或命令参数。`--timeout` 默认 180 秒，为模型传输超时设置。

   样例调用已有 HTTP API，要求后端与脚本共享文件系统：先创建环境，加载目录资源，将 `flows/similarity.json` 的资源/环境占位符解析为实际引用，以 `{name, flow}` 保存。执行使用完整内存快照。不会修改仓库默认配置。

3. 脚本等待终态，输出状态、服务/任务 ID、实际模式、usage 和两类报告。失败返回非零退出码及具体错误，不发布部分成功报告。`--output` 导出不含原输入、环境地址或凭据引用；模型 reason/suggestion 可能引用输入，分享报告前仍需审阅内容。
4. 终端 A 按 Ctrl+C 停止后端。桌面会话关闭窗口退出，立即中止本地模型传输。主动取消任务使用 `POST /api/v1/runs/{runId}/cancel`，会等当前模型传输结束，超时或断连仍为 failed。

默认实例配置是 loopLimit=1、tokenLimit=32768、strictTokenLimit=true。当前 OpenAI 兼容与 Ollama 适配器均没有输入 token 上界预检，严格模式会在发送前返回 `TOKEN_ACCOUNTING_UNSUPPORTED`。上例的 `--non-strict` 是显式选择，不是自动降级；仍执行 token 账本及超额检查。模型缺失可用 usage 时失败，不按零消耗处理。模型上下文容量由已有部署保证，平台不自动下载模型、扩大上下文或重试。

远程 API 默认使用 `max_completion_tokens` 和 JSON 模式，兼容服务可显式追加 `--output-token-parameter max_tokens` 或 `--no-json-mode`。baseUrl 不含 `/chat/completions`，平台追加该路径。完整启动和隐藏输入 Key 的命令见 [项目 README](../readme.md#快速启动)。

Ollama 用户须显式添加 `--adapter ollama-chat`，将 `--model-url` 改为服务根地址（如 `http://127.0.0.1:11434`），模型名填已有部署；不要求所有用户安装 Ollama。

## API 和桌面等价步骤

| 步骤 | 既有接口或动作 |
| --- | --- |
| 创建环境 | `POST /api/v1/environments`，模型连接 connectionId=model、kind=model、modelAdapter=openai-chat、baseUrl（含 /v1）、model；保存返回 environmentId |
| 加载模块 | `POST /api/v1/catalog/load`，包路径 `packages/semantic`、块路径 `blocks/clean.py`、`score.py`、`adapt.py`、`assemble.py` |
| 准备拼图 | 服务页面选择输入输出契约，拼清洗→计分→适配→语义→组装；逐节点明确来源，语义包弹窗绑定实际环境连接 |
| 保存服务 | `POST /api/v1/services`，`{name, flow: 完整FlowDraft}`；成功即生成当前实例与稳定 serviceId |
| 提交调用 | `POST /api/v1/runs`，`{serviceId, input: {targetText, comparisonTexts}}` |
| 状态和结果 | `GET /api/v1/runs/{runId}`；completed 后 `GET /api/v1/runs/{runId}/result` |

桌面环境页填写 Base URL 和凭据，获取并选择模型后保存。服务页操作参见 [查重拼图说明](assignment-similarity/README.md)。也可使用配方辅助导入草稿：

```bash
.venv/bin/python samples/flow_templates.py samples/assignment-similarity similarity --platform-url 实际后端地址 --environment-id 实际环境ID --non-strict
```

随后点击桌面“检查健康状态”刷新目录与草稿，从会话草稿选择“文本查重”，检查节点配置后“校验并保存实例版本”。无需手写 instance.json 或 capabilityBindings。路径由同机后端读取，不上传目录。

所有环境、凭据、配置版本、任务和报告仅在当前后端内存。重启需重新创建/加载，旧 runId 返回 404，历史不可回退；显式导出的 JSON 文件仍保留在磁盘，不会自动导入恢复。

## 模板与验证入口

- [标准模板](template/README.md)：单文件块、控制流及同包双节点配置；复制重命名验证：`.venv/bin/python checks/template_copy.py`。
- [查重产品](assignment-similarity/README.md)：算法边界与契约。
- 合成契约与清洗：`checks/similarity_contracts.py`、`checks/similarity_preprocessing.py`。
- 计分和现有 DOCX：`.venv/bin/python checks/similarity_scoring.py --artifact-dir artifact`，只在本地提取及计分，不调用模型、不提交原文。
- 新版查重拼图：`.venv/bin/python checks/similarity_flow.py`，使用本地 HTTP 替身；旧 `similarity_workflow.py` 仅属 I5 历史入口。
