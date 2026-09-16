"""顺序 LangGraph 构造入口；节点边界显式验证，不实现模型或预算。"""
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any
from langgraph.graph import END, START, StateGraph
from ..contracts import StrictModel


@dataclass(frozen=True)
class SequentialExecutor:
    state_model: type[StrictModel]
    graph: Any
    node_count: int

    async def run(self, value: Mapping[str, Any] | StrictModel) -> StrictModel:
        data = value.model_dump() if isinstance(value, StrictModel) else dict(value)
        initial = self.state_model.model_validate(deepcopy(data), strict=True)
        result = await self.graph.ainvoke(
            initial.model_dump(),
            config={'recursion_limit': self.node_count + 2},
        )
        return self.state_model.model_validate(deepcopy(result), strict=True)


def build_sequential(
    state_model: type[StrictModel],
    nodes: Sequence[tuple[str, Callable]],
) -> SequentialExecutor:
    """节点接收独立模型，返回以 Python 字段名为键的部分状态更新。"""
    if not nodes:
        raise ValueError('顺序图至少包含一个节点')
    names = [name for name, _ in nodes]
    if len(set(names)) != len(names) or any(not name or name in (START, END) for name in names):
        raise ValueError('图节点名必须非空、唯一且不能使用保留名')
    graph = StateGraph(state_model)

    def wrap(operation):
        async def checked(state):
            data = state.model_dump() if isinstance(state, StrictModel) else state
            validated = state_model.model_validate(deepcopy(data), strict=True)
            baseline = deepcopy(validated.model_dump())
            update = operation(validated)
            if isawaitable(update):
                update = await update
            # 拦截节点通过可变容器绕过赋值校验的非法修改。
            state_model.model_validate(validated.model_dump(), strict=True)
            if not isinstance(update, dict):
                raise TypeError('节点必须返回状态更新字典')
            if any(key not in state_model.model_fields for key in update):
                raise ValueError('节点状态更新包含未知字段或非 Python 字段名')
            merged = {**baseline, **deepcopy(update)}
            output = state_model.model_validate(merged, strict=True)
            return output.model_dump()
        return checked

    previous = START
    for name, operation in nodes:
        graph.add_node(name, wrap(operation), retry_policy=None, cache_policy=None)
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    compiled = graph.compile(checkpointer=None, cache=None, store=None)
    return SequentialExecutor(state_model, compiled, len(nodes))
