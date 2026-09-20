"""显式端口编译器：图状态只存已校验的值，模块只接收自己的输入。"""
import asyncio
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any
from pydantic import BaseModel, Field, ValidationError
from langgraph.graph import START, END, StateGraph
from langgraph.errors import GraphRecursionError
from ..contracts.base import StrictModel
from ..contracts.flows import FlowDraft, ModuleNode, ConstantValue, IfNode, RepeatNode, WhileNode, PortReference
from ..contracts.errors import PlatformError, ErrorResponse
from ..runtime.context import current_context
from ..runtime.boundary import checkpoint
from .validation import validate_flow

COMPILER_VERSION = 'flow-4'
execution_path = ContextVar('flow_path', default=())
step_counter = ContextVar('flow_steps', default=None)


async def boundary(phase, node):
    await asyncio.sleep(0)
    await checkpoint(phase, node)
    counter = step_counter.get()
    if phase == 'node_start' and counter is not None:
        counter[0] += 1
        if counter[0] > counter[1]:
            raise PlatformError(ErrorResponse(code='GRAPH_EXECUTION_LIMIT', stage='flow',
                node_id=node, message='图执行步数超过限制'))


def guarded(node_id, operation):
    async def run(state):
        await boundary('node_start', node_id)
        async def execute():
            result = operation(state)
            if isawaitable(result):
                result = await result
            await boundary('node_update', node_id)
            await boundary('edge', node_id)
            return result
        context = current_context.get()
        return await context.run_step('nodes.' + node_id, execute, kind='node') if context else await execute()
    return run


def plain(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode='json', by_alias=True)
    return deepcopy(value)


def checked(contract, value, stage):
    try:
        return contract.adapter.validate_python(plain(value), strict=True)
    except PlatformError as exc:
        if exc.error.code in ('CONTRACT_VALIDATION_ERROR', 'OUTPUT_VALIDATION_ERROR'):
            exc.error.stage = stage
            exc.error.code = 'OUTPUT_VALIDATION_ERROR' if stage.endswith('output') else 'CONTRACT_VALIDATION_ERROR'
        raise
    except ValidationError as exc:
        from ..validation_issues import validation_exception
        raise validation_exception(exc, stage=stage,
            code='OUTPUT_VALIDATION_ERROR' if stage.endswith('output') else 'CONTRACT_VALIDATION_ERROR') from None


def resolve(source, state):
    if isinstance(source, ConstantValue):
        return deepcopy(source.value)
    value = (state.input if source.kind == 'input' else
             state.carry[source.node_id] if source.kind == 'carry' else state.outputs[source.node_id])
    return deepcopy(value)


def bound_value(bindings, state):
    if len(bindings) != 1:
        raise PlatformError(ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='flow.source',
            message='请选择一个完整数据来源；字段映射和转换请添加通用块处理'))
    return resolve(bindings[0].source, state)


class FlowState(StrictModel):
    input: Any
    outputs: dict[str, Any] = Field(default_factory=dict)
    carry: dict[str, Any] = Field(default_factory=dict)
    result: Any = None


@dataclass(frozen=True)
class FlowExecutor:
    draft: FlowDraft
    catalog: object
    graph: object

    async def run(self, value, *, recursion_limit=10000):
        value = await asyncio.to_thread(checked, self.catalog.contract(self.draft.input_contract), value, 'flow.input')
        token = step_counter.set([0, recursion_limit])
        try:
            await boundary('start', 'flow')
            result = await self.graph.ainvoke({'input': plain(value)}, config={'recursion_limit': recursion_limit})
            await boundary('terminal', 'flow')
            return deepcopy(result['result'])
        except GraphRecursionError:
            raise PlatformError(ErrorResponse(code='GRAPH_EXECUTION_LIMIT', stage='flow', message='图执行步数超过限制')) from None
        finally:
            try:
                await checkpoint('cleanup', 'flow')
            finally:
                step_counter.reset(token)


def compile_flow(draft, catalog):
    draft = draft.model_copy(deep=True)
    validation = validate_flow(draft, catalog)
    if not validation.valid:
        error = ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='flow.compile',
            message='输入输出契约校验失败，请添加通用块完成转换并重新保存', issues=validation.issues)
        raise PlatformError(error)

    def wrap(node, source, next_contract=None, next_node=None):
        async def execute(state):
            stage = 'nodes.' + node.node_id
            try:
                view = catalog.get(node.artifact_ref)
                value = await asyncio.to_thread(checked, catalog.contract(view.input_contract), resolve(source, state), stage + '.input')
                context = current_context.get()
                if node.kind == 'block':
                    operation = lambda: catalog.artifact(node.artifact_ref).invoke(plain(value))
                    result = await context.invoke_block(node.node_id, plain(value)) if context else await operation()
                else:
                    if context is None:
                        raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage=stage, message='包执行需要任务上下文'))
                    result = await context.invoke_package(node.node_id, plain(value))
                result = await asyncio.to_thread(checked, catalog.contract(view.output_contract), result, stage + '.output')
                if next_contract:
                    try:
                        await asyncio.to_thread(checked, catalog.contract(next_contract), result, stage + '.output')
                    except PlatformError as exc:
                        exc.error.source_node_id = node.node_id
                        exc.error.message = ('输出不符合下一步输入契约' if next_node else '输出不符合服务输出契约') + '：' + exc.error.message
                        raise
                return {'outputs': {**deepcopy(state.outputs), node.node_id: plain(result)}}
            except PlatformError as exc:
                exc.error.node_id = node.node_id
                raise
        attempt = guarded(node.node_id, execute)
        async def run(state):
            for retry in range(draft.retry_limit + 1):
                try:
                    return await attempt(state)
                except PlatformError as exc:
                    if exc.error.code != 'OUTPUT_VALIDATION_ERROR' or not exc.error.stage.endswith('.output'):
                        raise
                    if retry == draft.retry_limit:
                        error = exc.error.model_copy(deep=True)
                        error.message = f'输出契约校验失败，已额外重试 {draft.retry_limit} 次：' + error.message
                        error.details.attempt = retry + 1
                        raise PlatformError(error) from None
        return run

    def sequence(nodes, incoming, final_contract=None):
        graph = StateGraph(FlowState)
        previous = START
        for index, node in enumerate(nodes):
            name = f'node_{index}'
            source = PortReference(kind='node', node_id=nodes[index - 1].node_id) if index else incoming
            if isinstance(node, ModuleNode):
                following = nodes[index + 1] if index + 1 < len(nodes) else None
                expected = (catalog.get(following.artifact_ref).input_contract if isinstance(following, ModuleNode)
                            else final_contract if following is None else None)
                graph.add_node(name, wrap(node, source, expected, following), retry_policy=None)
                graph.add_edge(previous, name)
                previous = name
            elif isinstance(node, IfNode):
                branches = {True: (sequence(node.then_branch.nodes, source), node.then_branch.output),
                            False: (sequence(node.else_branch.nodes, source), node.else_branch.output)}
                def chooser(node):
                    def choose(state):
                        value = resolve(node.condition, state)
                        if type(value) is not bool:
                            raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='flow.condition',
                                node_id=node.node_id, message='条件输出必须为严格 bool'))
                        return 'true' if value else 'false'
                    return choose
                def branch_run(node, compiled, bindings):
                    async def run(state):
                        child = await compiled.ainvoke(state.model_dump())
                        value = await asyncio.to_thread(checked, catalog.contract(node.output_contract),
                            bound_value(bindings, FlowState.model_validate(child)), 'nodes.' + node.node_id + '.output')
                        return {'outputs': {**deepcopy(state.outputs), node.node_id: plain(value)}}
                    return run
                graph.add_node(name, guarded(node.node_id, lambda state: {}))
                graph.add_edge(previous, name)
                for decision, (compiled, bindings) in branches.items():
                    graph.add_node(name + ('_true' if decision else '_false'), guarded(node.node_id, branch_run(node, compiled, bindings)))
                graph.add_conditional_edges(name, chooser(node), {'true': name + '_true', 'false': name + '_false'})
                graph.add_node(name + '_join', guarded(node.node_id, lambda state: {}))
                graph.add_edge(name + '_true', name + '_join')
                graph.add_edge(name + '_false', name + '_join')
                previous = name + '_join'
            else:
                child = sequence(node.body, PortReference(kind='carry', node_id=node.node_id))
                condition_graph = sequence([node.condition], PortReference(kind='carry', node_id=node.node_id)) if isinstance(node, WhileNode) else None
                def loop_run(node, child, condition_graph):
                    async def run(state):
                        contract = catalog.contract(node.carry.contract)
                        carried = await asyncio.to_thread(checked, contract, bound_value(node.carry.initial, state), 'nodes.' + node.node_id + '.input')
                        iteration = 0
                        while True:
                            await boundary('node_start', node.node_id)
                            await boundary('edge', node.node_id)
                            inner = state.model_copy(deep=True)
                            inner.carry[node.node_id] = plain(carried)
                            if isinstance(node, RepeatNode):
                                if iteration >= node.count:
                                    break
                            else:
                                path_token = execution_path.set((*execution_path.get(), f'{node.node_id}[{iteration}].condition'))
                                try:
                                    condition_state = await condition_graph.ainvoke(inner.model_dump())
                                finally:
                                    execution_path.reset(path_token)
                                decision = condition_state['outputs'][node.condition.node_id]
                                if type(decision) is not bool:
                                    raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='flow.condition',
                                        node_id=node.node_id, message='条件输出必须为严格 bool'))
                                if not decision:
                                    break
                                if iteration >= node.max_iterations:
                                    raise PlatformError(ErrorResponse(code='LOOP_ITERATION_LIMIT', stage='flow.loop',
                                        node_id=node.node_id, message='达到最大次数后循环条件仍为 true'))
                            path_token = execution_path.set((*execution_path.get(), f'{node.node_id}[{iteration}]'))
                            try:
                                updated = await child.ainvoke(inner.model_dump())
                            finally:
                                execution_path.reset(path_token)
                            carried = await asyncio.to_thread(checked, contract, bound_value(node.carry.update, FlowState.model_validate(updated)),
                                'nodes.' + node.node_id + '.output')
                            iteration += 1
                        return {'outputs': {**deepcopy(state.outputs), node.node_id: plain(carried)}}
                    return run
                graph.add_node(name, guarded(node.node_id, loop_run(node, child, condition_graph)))
                graph.add_edge(previous, name)
                previous = name
        graph.add_edge(previous, END)
        return graph.compile(checkpointer=None)

    graph = StateGraph(FlowState)
    compiled = sequence(draft.flow, PortReference(kind='input'), draft.output_contract)
    async def body(state):
        return await compiled.ainvoke(state.model_dump())
    graph.add_node('body', body)
    graph.add_edge(START, 'body')
    async def output(state):
        result = await asyncio.to_thread(checked, catalog.contract(draft.output_contract), state.outputs[draft.flow[-1].node_id], 'flow.output')
        return {'result': plain(result)}

    graph.add_node('output', guarded('output', output))
    graph.add_edge('body', 'output')
    graph.add_edge('output', END)
    return FlowExecutor(draft, catalog, graph.compile(checkpointer=None))
