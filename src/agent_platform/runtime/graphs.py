"""顺序 LangGraph 构造入口；节点边界显式验证，不实现模型或预算。"""
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any
from langgraph.graph import END, START, StateGraph
from langgraph.errors import GraphRecursionError
from ..contracts.errors import PlatformError, ErrorResponse
from ..contracts import StrictModel
from .boundary import Boundary, checkpoint, current_boundary


@dataclass(frozen=True)
class SequentialExecutor:
    state_model: type[StrictModel]
    graph: Any
    node_count: int

    async def run(self, value: Mapping[str, Any] | StrictModel, *, boundary=None) -> StrictModel:
        inherited = current_boundary.get()
        if boundary is not None and inherited is not None and boundary is not inherited:
            boundary = Boundary(boundary.policies, boundary.observer, parent=inherited)
        token = current_boundary.set(boundary or inherited or Boundary())
        try:
            await checkpoint('start', 'graph')
            data = value.model_dump() if isinstance(value, StrictModel) else dict(value)
            initial = self.state_model.model_validate(deepcopy(data), strict=True)
            result = await self.graph.ainvoke(
                initial.model_dump(), config={'recursion_limit': self.node_count + 2})
            output = self.state_model.model_validate(deepcopy(result), strict=True)
            await checkpoint('terminal', 'graph')
            return output
        except GraphRecursionError:
            raise PlatformError(ErrorResponse(code='GRAPH_EXECUTION_LIMIT', stage='graph', message='图执行步数超过限制')) from None
        finally:
            try:
                await checkpoint('cleanup', 'graph')
            finally:
                current_boundary.reset(token)


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

    def wrap(name, operation):
        async def checked(state):
            await checkpoint('node_start', name)
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
            await checkpoint('node_update', name)
            await checkpoint('edge', name)
            return output.model_dump()
        async def recorded(state):
            from .context import current_context
            context = current_context.get()
            if context is None:
                return await checked(state)
            return await context.run_step('nodes.' + name, lambda: checked(state), kind='node')
        return recorded

    previous = START
    for name, operation in nodes:
        graph.add_node(name, wrap(name, operation), retry_policy=None, cache_policy=None)
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    compiled = graph.compile(checkpointer=None, cache=None, store=None)
    return SequentialExecutor(state_model, compiled, len(nodes))
