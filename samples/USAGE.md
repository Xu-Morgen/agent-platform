# 加载、接线和调用模板

以下命令在仓库根目录执行，使用现有 `.venv` 依赖。桌面可按主 README 启动；也可先在独立终端运行 API：

```bash
.venv/bin/python -m agent_platform --host 127.0.0.1 --port 8000
```

API 文档在 `http://127.0.0.1:8000/docs`。桌面显示的后端地址可能不是 8000；两次启动是独立会话，资源 ID、环境和任务不能跨会话复用。

## 1. 三种加载请求

统一 `POST /api/v1/catalog/load`：

```json
{"kind":"block","path":"/absolute/path/samples/blocks/minimal.py"}
```

```json
{"kind":"package","path":"/absolute/path/samples/packages/minimal"}
```

```json
{"kind":"contract","path":"/absolute/path/samples/contracts/minimal.py","symbol":"Text"}
```

| 字段 | 作用 |
| --- | --- |
| kind | block/package/contract，决定加载方式 |
| path | 后端可读路径；块/契约选文件，包选目录；推荐绝对路径 |
| symbol | 契约必填，为文件中导出的类型名称；块/包省略 |

块/包返回 resourceId、inputContract、outputContract 和 schemas；包另有 configurationContract、budgetDefaults。API 块另有 apiRequired=true，需要在节点上配置 API 连接和请求路径 api.path。独立契约直接用 resourceId 作为端口引用，schemas.value 展示类型。

## 2. 可直接执行的最小闭环

这段代码会向上面运行中的后端加载最小块与独立契约、创建一个服务并提交一次真实纯块任务，不依赖模型或外部 API：

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import time
import httpx

with httpx.Client(base_url='http://127.0.0.1:8000', timeout=10) as client:
    def post(path, body):
        response = client.post('/api/v1/' + path, json=body)
        response.raise_for_status()
        return response.json()

    block = post('catalog/load', {
        'kind': 'block', 'path': str(Path('samples/blocks/minimal.py').resolve()),
    })
    contract = post('catalog/load', {
        'kind': 'contract', 'path': str(Path('samples/contracts/minimal.py').resolve()),
        'symbol': 'Text',
    })
    flow = {
        'name': '最小文本整理',
        'inputContract': contract['resourceId'],
        'outputContract': contract['resourceId'],
        'flow': [{
            'nodeId': 'trim', 'kind': 'block', 'artifactRef': block['resourceId'],
        }],
    }
    validation = post('flows/validate', {'content': flow})
    if not validation['valid']:
        raise RuntimeError(validation['issues'])
    service = post('services', {'name': flow['name'], 'flow': flow})
    run = post('runs', {'serviceId': service['serviceId'], 'input': {'text': '  hello  '}})
    for _ in range(100):
        response = client.get('/api/v1/runs/' + run['runId'])
        response.raise_for_status()
        state = response.json()
        if state['status'] in ('completed', 'failed', 'cancelled'):
            if state['status'] != 'completed':
                raise RuntimeError(state)
            response = client.get('/api/v1/runs/' + run['runId'] + '/result')
            response.raise_for_status()
            print(response.json())  # 结果中的业务输出为 {"text": "hello"}。
            break
        time.sleep(0.1)
    else:
        raise TimeoutError('任务尚未结束，请根据 runId 查询状态')
PY
```

这里独立契约 Text 与块的 Text 都是无自定义校验的相同结构，因此可以直接接线。若不需要独立契约，也可把服务 inputContract/outputContract 分别设为块返回的对应引用。

## 3. 包与 API 通用块如何组成服务

把上述 flow 中的 block 节点换为已加载的 package，nodeId 设为 summarize；服务端口选该包的 inputContract/outputContract，出口 source.nodeId 同步改为 summarize。

在同一 FlowDraft 顶层加入：

```json
{
  "nodeConfigurations": {
    "summarize": {
      "parameters": {},
      "budget": {"loopLimit": 4, "tokenLimit": 32768},
      "model": {"environmentId": "replace-environment-id", "connectionId": "replace-model-connection-id"},
      "maxOutputTokens": 512
    }
  },
  "budget": {"loopLimit": 4, "tokenLimit": 32768}
}
```

这是待合并的配置片段，替换实际 ID 后再发送；不是完整保存服务请求。完整包则使用其 [节点配置示例](packages/complete/node-configuration.example.json)。包的创建步骤见 [packages/README.md](packages/README.md)。

### 最完整通用块的节点配置

加载 `samples/blocks/complete.py`，使用其 inputContract/outputContract 作为服务端口，将块节点命名为 normalize，并将服务完整输入传给块节点，平台自动返回该节点的完整输出。在同一 FlowDraft 顶层加入：

```json
{
  "nodeConfigurations": {
    "normalize": {
      "api": {
        "environmentId": "replace-environment-id",
        "connectionId": "lookup",
        "path": "/lookup"
      }
    }
  }
}
```

替换为实际 API 环境和连接 ID；path 必填，为该连接 Base URL 下的请求路径。环境保存 Base URL、凭据和超时，节点保存路径；方法、请求参数和响应契约由块定义。该片段不是完整的服务保存请求。只有通用块时不需要模型连接或任务预算。

输入示例为 `{"query":"greeting"}`（query 不能全为空白），可另带 options 和可选任务附件；`options.requireContent=true` 时拒绝整理后为空白的正文。块使用 `api.request('GET', {'query': value.query}, response_type=APIResponse)`，请求节点配置的路径。若 Base URL 是 `https://example.com/api`，实际请求为 `https://example.com/api/lookup?query=greeting`；这是配置示意，项目不提供此远端服务。响应要求及选项见 [完整块说明](blocks/README.md#最完整实现)。

完整块会上报 API 等待消息及三个处理阶段的实际进度；进度不加入业务输出，不代表整个任务成功。

修改路径后保存实例版本即可生效，无需修改块源码；已提交任务继续使用原路径，历史回退恢复历史节点路径。旧 API 节点配置需补充 api.path，旧块的 api.request 调用需移除路径参数。

## 4. FlowDraft 的公共配置

| 字段 | 必填/默认 | 作用 |
| --- | --- | --- |
| draftId | 可省略 | 可选草稿标记，不是可调用的 serviceId |
| name | 必填，非空 | 流程名称 |
| inputContract / outputContract | 必填 | 已加载的服务端口契约引用 |
| flow | 必填列表 | 顺序执行的节点及控制容器 |
| retryLimit | 默认 3，整数 0～1000 | 运行时输出不符合契约时的最大额外重试次数；0 表示不重试，声明类型不兼容直接拒绝保存 |
| nodeConfigurations | 默认 {} | 按 nodeId 保存包的模型配置或 API 通用块的连接与请求路径配置；普通计算块和控制容器无需配置 |
| budget | 默认 null；含包必填 | 全局 loop/token 累计限额 |
| examples | 默认 [] | 每项 `{name, input}`，示例输入供界面使用，不是自动测试或自动执行 |

### 块/包节点

| 字段 | 作用 |
| --- | --- |
| nodeId | 整个流程内唯一，以英文字母开头，仅字母/数字/下划线/连字符 |
| kind | block/package |
| artifactRef | 对应加载结果 resourceId |

### 分支与循环的数据来源

| 字段 | 作用 |
| --- | --- |
| source.kind=input | 引用服务输入，不填 nodeId |
| source.kind=node | 引用可见前序节点输出，必须填 nodeId |
| source.kind=carry | 引用循环当前携带值，nodeId 填循环节点 ID |
| source.kind=constant | 直接填符合接收方契约的完整 value，不填 nodeId/path |

业务包和通用块不声明 inputs，也不选择数据来源；输入输出契约由其代码或清单固定声明。第一步接收服务完整输入，之后只接收上一层完整输出；分支内第一步接收进入分支前的完整数据，循环体和循环条件通用块的第一步接收本轮完整携带值。平台只传递完整数据，不支持字段路径引用、改名或拼装。分支与循环配置中的每条来源只声明 source；API 节点的请求路径 api.path 保持不变。来源完整输出与接收方契约不兼容时校验报错，例如 answer 无法直接传入要求 text 的契约；请在两步之间添加通用块完成转换。分支输出、循环初始值和更新值也遵循同一规则。服务返回只配置 outputContract，自动使用顶层流程最后一步的完整输出，不声明 output 或手动选择返回来源；空流程不能保存为服务。不提供旧字段映射的兼容或迁移。

### 控制容器字段

| kind | 配置 | 语义 |
| --- | --- | --- |
| if | nodeId、condition、outputContract、thenBranch、elseBranch | condition 引用严格 bool；两条分支均有 nodes（默认 []）和必填 output 接线，共用出口契约 |
| repeat | nodeId、count、carry、body | count 为非负整数；body 默认 []；0 次返回初始 carry |
| while | nodeId、maxIterations、condition、carry、body | condition 是一个 kind=block 的完整节点，输出严格 bool；body 默认 []；maxIterations 是正整数 |
| carry | contract、initial、update | 携带值类型、初始接线、每轮结束更新接线，三项均必填 |

if.condition 是端口引用；while.condition 是实际执行条件检查的块节点，两者格式不同。while 达到上限后条件仍为真会失败。循环体以 carry 读当前状态；外部从容器节点出口读取结果，不能越过作用域读取内部节点。这些是服务编排字段，不是资源或包生命周期钩子。

## 5. 保存、版本与外部调用

| 操作 | API 与请求体 |
| --- | --- |
| 保存草稿 | POST /api/v1/drafts，`{content: FlowDraft}`；允许未完成内容 |
| 预检 | POST /api/v1/flows/validate，`{content: FlowDraft}`；检查返回 valid/issues |
| 创建稳定服务 | POST /api/v1/services，`{name, flow: FlowDraft}` |
| 保存新实例版本 | POST /api/v1/services/{serviceId}/versions，同上 |
| 获取业务契约 | GET /api/v1/services/{serviceId}/schema |
| 提交任务 | POST /api/v1/runs，`{serviceId, input}`；可带 expectedInstanceId |
| 查询状态/结果 | GET /api/v1/runs/{runId}；GET /api/v1/runs/{runId}/result |
| 取消任务 | POST /api/v1/runs/{runId}/cancel |

草稿不可直接调用；保存实例成功后稳定服务入口立即指向新版本。已提交任务固定代码、配置及实际环境。更新/退出语义和内存存储边界见 [项目说明](../readme.md)。

## 文件输入与运行环境

任务输入契约使用 `TaskFile` 的字段会显示 PDF/DOCX 选择控件；先保存文件，再提交任务，其他字段继续使用 JSON。任务文件副本与任务记录绑定，源文件移动不会影响任务；未提交上传保留 24 小时，历史任务附件保留到显式管理。

加载通用块会先静态读取 `@block` 字面量声明，再锁定依赖、准备独立环境和模型缓存，最后在对应 Python 子进程中导入与校验。页面显示实际阶段、来源和下载字节，可取消并重新加载重试；此准备不计业务 loop。完整模板仍使用空依赖及空模型清单，无需 OCR 下载。规范见 [平台运行文件与依赖](../docs/platform-runtime-files.md)。

## 文档业务组合

独立的 [文档出题实例](../examples/document-question-generation/README.md) 演示 PDF/DOCX 上传、本地 OCR、整份资料输入和线上模型出题，不改变本目录三类模板的用途。成功结果只包含题目；资料不足按平台失败协议终止，题目结构错误按 retryLimit 重试本包，全文不静默截断。
