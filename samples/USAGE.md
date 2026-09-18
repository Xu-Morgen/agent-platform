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

块/包返回 resourceId、inputContract、outputContract 和 schemas；包另有 configurationContract、budgetDefaults。独立契约直接用 resourceId 作为端口引用，schemas.value 展示类型。

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
            'inputs': [{'target': [], 'source': {'kind': 'input', 'path': []}}],
        }],
        'output': [{'target': [], 'source': {'kind': 'node', 'nodeId': 'trim', 'path': []}}],
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

## 3. 包节点如何组成服务

把上述 flow 中的 block 节点换为已加载的 package，nodeId 设为 summarize；服务端口选该包的 inputContract/outputContract，出口 source.nodeId 同步改为 summarize。

在同一 FlowDraft 顶层加入：

```json
{
  "nodeConfigurations": {
    "summarize": {
      "parameters": {},
      "budget": {"loopLimit": 1, "tokenLimit": 32768},
      "model": {"environmentId": "replace-environment-id", "connectionId": "replace-model-connection-id"},
      "maxOutputTokens": 512
    }
  },
  "budget": {"loopLimit": 1, "tokenLimit": 32768, "strictTokenLimit": false}
}
```

这是待合并的配置片段，替换实际 ID 后再发送；不是完整保存服务请求。完整包则使用其 [节点配置示例](packages/complete/node-configuration.example.json)。包的创建步骤见 [packages/README.md](packages/README.md)。

## 4. FlowDraft 的公共配置

| 字段 | 必填/默认 | 作用 |
| --- | --- | --- |
| draftId | 可省略 | 可选草稿标记，不是可调用的 serviceId |
| name | 必填，非空 | 流程名称 |
| inputContract / outputContract | 必填 | 已加载的服务端口契约引用 |
| flow | 必填列表 | 顺序执行的节点及控制容器 |
| output | 必填接线列表 | 将可见数据绑定到服务出口 |
| nodeConfigurations | 默认 {} | 按 nodeId 保存包配置；块和控制容器不在这里配置 |
| budget | 默认 null；含包必填 | 全局 loop/token 预算及严格模式 |
| examples | 默认 [] | 每项 `{name, input}`，示例输入供界面使用，不是自动测试或自动执行 |

### 块/包节点

| 字段 | 作用 |
| --- | --- |
| nodeId | 整个流程内唯一，以英文字母开头，仅字母/数字/下划线/连字符 |
| kind | block/package |
| artifactRef | 对应加载结果 resourceId |
| inputs | 接线列表，默认 []；按目标输入模型填充 |

### 每条接线

| 字段 | 作用 |
| --- | --- |
| target | 目标字段路径，默认 [] 表示整个输入/出口 |
| source.kind=input | 引用服务输入，不填 nodeId |
| source.kind=node | 引用可见前序节点输出，必须填 nodeId |
| source.kind=carry | 引用循环当前携带值，nodeId 填循环节点 ID |
| source.path | 源字段路径，默认 [] 表示整个值 |
| source.kind=constant | 直接填 value，不填 nodeId/path |

路径是字符串/非负整数数组，如 `["text"]`、`["items",0,"text"]`；对象路径使用对外 JSON 字段名。可选字段或无法证明存在的数组项不能直接读取。结构不一致时使用转换块，平台不会自动改名或宽松转换。

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
