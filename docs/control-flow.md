# 数组遍历与枚举分支

当前执行协议为 `flow-6`。服务页支持顺序、if/else、repeat、while、foreach 和 switch；流程、路由代码和分支由配置者预先定义。模型只返回业务数据，不能生成或修改可执行流程。实现与验证记录见[归档计划](archive/2026-09-21/control-flow-expansion-plan.md)。

## 数组遍历 foreach

1. 从「控制」分类或流程的 ＋ 插入「数组遍历」。
2. 选择完整来源：服务输入、作用域内已执行节点、外层循环携带值或外层 foreach 当前元素。
3. 从来源 Schema 列出的数组字段中选择路径。根数组选择 `[]`；嵌套对象如 `payload → values` 对应 `arrayPath: ["payload", "values"]`。只支持确定、必填的对象字段；可空、联合或动态结构应先用通用块规范化，不支持数组下标、通配符或表达式。
4. 设置最大条数和每项输出契约，添加非空循环体。首步 primary 是当前元素，默认零参考；完整请求等上下文在「高级参考」中显式绑定。
5. 检查元素输入和汇总输出预览。每项返回循环体最后一步的完整输出；容器输出固定为 `{"items": [...]}`，按输入顺序汇总，集合 Schema 从元素输出契约派生。

进入容器时复制数组。长度超过 `maxItems` 时在第一项前失败，不截断；空数组返回 `{"items": []}`。需要非空集合的下游不能假定至少执行一次。foreach 没有可更新 carry，也不向元素中加入索引；每轮重新建立独立作用域，不能读取上一轮遗留节点结果。嵌套体可显式引用可见外层的完整当前元素。

foreach 后的普通节点默认参考是进入 foreach 时的完整主数据，与所选数组来源可能不同；默认参考不是最后一项。普通节点仍不提供字段选取、改名和合并。

## 枚举分支 switch

1. 插入「枚举分支」，选择输出为有限字符串 `Literal` 的 Python 通用块作为路由。
2. 首次选择路由块时自动创建其全部枚举分支。节点始终展示枚举出口列表，各分支标题明确显示「路由结果为 …」，收起配置也可查看。更换路由后若出口不匹配，页面标出待创建或已失效的值，点击「按路由枚举同步出口」调整；已有同名分支配置保留。每个值必须有且只有一个分支，保存时拒绝缺少、重复或额外出口，无隐式 default。
3. 选择统一输出契约，分别配置分支内步骤和完整出口来源。空分支也必须显式选择一个兼容的完整来源。
4. 路由块的 primary/references 与容器入口一致。路由值只选择路径，不替换业务主数据；一次只执行一个分支，外层只得到容器的完整输出。

例如，模型返回审题结果后，Python 路由块可返回 `Literal['pass', 'revise', 'regenerate', 'insufficient_source']`；对应路线均须在页面预先配置。if/while 仍要求严格 bool，不能用字符串代替。

下面的独立路由块可与现有 `samples/blocks/minimal.py` 配合教学。保存为自己的 Python 资源文件，通过页面加载；它没有额外依赖，不调用模型。

```python
from typing import Literal
from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput

class Text(StrictModel):
    text: str

@block(id='text-route', version='1.0.0', name='文本处理路由')
def route(value: NodeInput[Text, tuple[()]]) -> Literal['trim', 'keep']:
    return 'trim' if value.primary.text.strip() != value.primary.text else 'keep'
```

用以下独立契约文件声明服务输入与返回值。页面分别以 `Request` 和 `Results` 为契约类名加载；内部集合仍由 foreach 推导，不由用户额外配置另一份集合端口。

```python
from agent_platform.contracts.base import StrictModel

class Text(StrictModel):
    text: str

class Request(StrictModel):
    values: list[Text]

class Results(StrictModel):
    items: list[Text]
```

在页面选择 Request → foreach（数组 `values`，元素输出 Text）→ switch（路由为上述块，统一输出 Text）。trim 分支加入「去掉首尾空白」块并绑定其输出；keep 分支保留空体，出口绑定外层 foreach「当前元素」。服务输出选择 Results。输入 `{"values": [{"text": " a "}, {"text": "b"}]}` 返回 `{"items": [{"text": "a"}, {"text": "b"}]}`。所有资源加载、接线和实例保存均通过正式页面完成。

## 作用域、预算与失败

- 来源不能前向、跨分支、越过容器作用域、跨服务或读取其他轮次的残留值；参考列表只传完整数据。
- 容器内部可组合其他控制节点及一层固定叶子服务。元素失败则整个任务失败，已完成步骤记录保留，不返回伪装成功的部分结果。
- 使用同一任务的 loop/token、取消和图步数边界；元素数量不等于模型调用次数，每次模型调用尝试仍单独计 loop。
- 契约失败只重试现有规则允许的生产节点；路由块输出失败可按 retryLimit 重试。集合或容器后入口失败不整体重放容器，不重试无关历史来源。
- 步骤路径包含 `容器ID[元素索引]`，索引从 0 开始；switch 路径包含所选枚举值。正常取消与应用退出、中断恢复沿用[持久化说明](persistence.md)。

## 协议升级

flow-5 及更早实例保留原始身份、源码、摘要与历史引用，仅可查看；不能复制、执行或回退激活。请通过服务页重新配置并保存 flow-6 新实例。已有 NodeInput 资源声明无需仅为本次协议升级修改版本；如果更改资源内容，仍须按资源版本规则重新导入。含固定子服务的父流程先重新保存叶子服务，再明确选择其新实例，不自动替换旧引用。

本轮通过离线边界断言、真实 Python 子进程、正式 Electron 配置保存及隔离 PostgreSQL 停库重启验证；没有调用外部模型，不表示 RAG 或黑神话业务实验已经完成。
