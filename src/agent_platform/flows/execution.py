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
from ..contracts.flows import FlowDraft, ModuleNode, ServiceNode, ConstantValue, IfNode, RepeatNode, WhileNode, ForeachNode, SwitchNode, PortReference
from ..contracts.errors import PlatformError, ErrorResponse
from ..runtime.context import current_context
from ..runtime.boundary import checkpoint
from .validation import validate_flow

COMPILER_VERSION = 'flow-6'
execution_path = ContextVar('flow_path', default=())
step_counter = ContextVar('flow_steps', default=None)
terminal_check = ContextVar('flow_terminal_check', default=None)


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
    if isinstance(source, tuple):
        return deepcopy(state.primaries[source[1]])
    if isinstance(source, ConstantValue):
        return deepcopy(source.value)
    value = (state.input if source.kind == 'input' else
             state.carry[source.node_id] if source.kind == 'carry' else
             state.items[source.node_id] if source.kind == 'item' else state.outputs[source.node_id])
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
    items: dict[str, Any] = Field(default_factory=dict)
    primaries: dict[str, Any] = Field(default_factory=dict)
    result: Any = None


@dataclass(frozen=True)
class FlowExecutor:
    draft: FlowDraft
    catalog: object
    graph: object

    async def run(self, value, *, recursion_limit=10000, output_check=None):
        value = await asyncio.to_thread(checked, self.catalog.contract(self.draft.input_contract), value, 'flow.input')
        token = step_counter.set(step_counter.get() or [0, recursion_limit])
        output_token = terminal_check.set(output_check)
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
                terminal_check.reset(output_token)


def compile_flow(draft, catalog):
    draft = draft.model_copy(deep=True)
    validation = validate_flow(draft, catalog)
    if not validation.valid:
        error = ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='flow.compile',
            message='输入输出契约校验失败，请添加通用块完成转换并重新保存', issues=validation.issues)
        raise PlatformError(error)

    def envelope(node, source, defaults, state):
        references = defaults if node.references is None else node.references
        try:
            return {'primary': resolve(source, state), 'references': [resolve(ref, state) for ref in references]}
        except KeyError:
            raise PlatformError(ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='nodes.' + node.node_id + '.references',
                node_id=node.node_id, message='本次执行的参考来源不可用')) from None

    async def validate_consumer(node, source, defaults, state, producer):
        try:
            if isinstance(node, ServiceNode):
                child = catalog.service(node)
                await asyncio.to_thread(checked, child.catalog.contract(child.draft.input_contract),
                                        resolve(source, state), 'nodes.' + node.node_id + '.input')
            else:
                await asyncio.to_thread(checked, catalog.contract(catalog.get(node.artifact_ref).input_contract),
                                        envelope(node, source, defaults, state), 'nodes.' + node.node_id + '.input')
        except PlatformError as exc:
            # 仅 primary 的字段错误可归因于直接生产者；参考和跨字段错误立即失败。
            paths = [issue.field_path for issue in exc.error.issues] or [exc.error.field_path or []]
            if exc.error.code in ('CONTRACT_VALIDATION_ERROR', 'OUTPUT_VALIDATION_ERROR') and (
                    isinstance(node, ServiceNode) or (paths and all(path and path[0] == 'primary' for path in paths))):
                exc.error.code = 'OUTPUT_VALIDATION_ERROR'
                exc.error.stage = 'nodes.' + producer + '.output'
                exc.error.source_node_id = producer
            exc.error.node_id = node.node_id
            raise

    def wrap(node, source, defaults, next_contract=None, next_node=None, *, terminal=False):
        async def execute(state):
            stage = 'nodes.' + node.node_id
            try:
                view = catalog.get(node.artifact_ref)
                value = await asyncio.to_thread(checked, catalog.contract(view.input_contract), envelope(node, source, defaults, state), stage + '.input')
                context = current_context.get()
                if node.kind == 'block':
                    operation = lambda: catalog.artifact(node.artifact_ref).invoke(plain(value))
                    result = await context.invoke_block(node.node_id, plain(value)) if context else await operation()
                else:
                    if context is None:
                        raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage=stage, message='包执行需要任务上下文'))
                    result = await context.invoke_package(node.node_id, plain(value))
                result = await asyncio.to_thread(checked, catalog.contract(view.output_contract), result, stage + '.output')
                updated = state.model_copy(deep=True)
                updated.outputs[node.node_id] = plain(result)
                updated.primaries[node.node_id] = deepcopy(plain(value)['primary'])
                if isinstance(next_node, (ModuleNode, ServiceNode)):
                    await validate_consumer(next_node, PortReference(kind='node', node_id=node.node_id),
                                            [('primary', node.node_id)], updated, node.node_id)
                elif isinstance(next_node, (IfNode, SwitchNode)):
                    await validate_consumer(next_node.condition if isinstance(next_node, IfNode) else next_node.router, PortReference(kind='node', node_id=node.node_id),
                                            [('primary', node.node_id)], updated, node.node_id)
                if next_contract:
                    try:
                        await asyncio.to_thread(checked, catalog.contract(next_contract), result, stage + '.output')
                    except PlatformError as exc:
                        exc.error.source_node_id = node.node_id
                        exc.error.message = ('输出不符合下一步输入契约' if next_node else '输出不符合服务输出契约') + '：' + exc.error.message
                        raise
                    if terminal and terminal_check.get():
                        try:
                            await terminal_check.get()(plain(result))
                        except PlatformError as exc:
                            if exc.error.code == 'OUTPUT_VALIDATION_ERROR':
                                exc.error.stage = stage + '.output'
                                exc.error.code = 'OUTPUT_VALIDATION_ERROR'
                                context = current_context.get()
                                exc.error.source_node_id = context.qualified(node.node_id) if context else node.node_id
                                exc.error.node_id = exc.error.source_node_id
                            raise
                return {'outputs': updated.outputs, 'primaries': updated.primaries}
            except PlatformError as exc:
                exc.error.node_id = exc.error.node_id or node.node_id
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

    def service_wrap(node, source, next_contract, next_node):
        async def execute(state):
            child = catalog.service(node)
            incoming = resolve(source, state)
            async def output_check(value):
                updated = state.model_copy(deep=True)
                updated.outputs[node.node_id] = plain(value)
                updated.primaries[node.node_id] = deepcopy(incoming)
                consumer = (next_node.condition if isinstance(next_node, IfNode) else
                            next_node.router if isinstance(next_node, SwitchNode) else next_node)
                if isinstance(consumer, (ModuleNode, ServiceNode)):
                    await validate_consumer(consumer, PortReference(kind='node', node_id=node.node_id),
                                            [('primary', node.node_id)], updated, node.node_id)
                if next_contract:
                    await asyncio.to_thread(checked, catalog.contract(next_contract), value, 'nodes.' + node.node_id + '.output')
            context = current_context.get()
            ct = None
            if context:
                from .context import FlowRunContext
                nested = FlowRunContext(context.run_id, child, context.runs, context.model,
                                        context.token_policy, context.api_transport)
                nested.prefix = context.qualified(node.node_id) + '/'
                nested.files = getattr(context, 'files', None)
                ct = current_context.set(nested)
            pt = execution_path.set((*execution_path.get(), (context.qualified(node.node_id) if context else node.node_id)))
            try:
                result = await child.graph.run(incoming, output_check=output_check)
            except PlatformError as exc:
                exc.error.node_id = exc.error.node_id or (context.qualified(node.node_id) if context else node.node_id)
                raise
            finally:
                execution_path.reset(pt)
                if ct is not None:
                    current_context.reset(ct)
            # 控制容器作为最后一步时也必须检查跨服务边界，但不重放整个子流程。
            if not isinstance(child.draft.flow[-1], ModuleNode):
                await output_check(result)
            return {'outputs': {**deepcopy(state.outputs), node.node_id: plain(result)},
                    'primaries': {**deepcopy(state.primaries), node.node_id: deepcopy(incoming)}}
        return guarded(node.node_id, execute)

    def sequence(nodes, incoming, final_contract=None, incoming_defaults=(), *, terminal=False):
        graph = StateGraph(FlowState)
        previous = START
        for index, node in enumerate(nodes):
            name = f'node_{index}'
            source = PortReference(kind='node', node_id=nodes[index - 1].node_id) if index else incoming
            defaults = [('primary', nodes[index - 1].node_id)] if index else incoming_defaults
            if isinstance(node, (ModuleNode, ServiceNode)):
                following = nodes[index + 1] if index + 1 < len(nodes) else None
                expected = final_contract if following is None else None
                operation = service_wrap(node, source, expected, following) if isinstance(node, ServiceNode) else wrap(node, source, defaults, expected, following, terminal=terminal)
                graph.add_node(name, operation, retry_policy=None)
                graph.add_edge(previous, name)
                previous = name
            elif isinstance(node, (IfNode, SwitchNode)):
                branches = {True: (sequence(node.then_branch.nodes, source, incoming_defaults=defaults), node.then_branch.output),
                            False: (sequence(node.else_branch.nodes, source, incoming_defaults=defaults), node.else_branch.output)} if isinstance(node, IfNode) else {
                            case.value: (sequence(case.nodes, source, incoming_defaults=defaults), case.output) for case in node.cases}
                routing_node = node.condition if isinstance(node, IfNode) else node.router
                condition_run = wrap(routing_node, source, defaults)
                def if_run(node, branches, condition_run, source, routing_node):
                    async def run(state):
                        token = execution_path.set((*execution_path.get(), node.node_id + ('.condition' if isinstance(node, IfNode) else '.router')))
                        try:
                            condition_state = await condition_run(state.model_copy(deep=True))
                        finally:
                            execution_path.reset(token)
                        decision = condition_state['outputs'][routing_node.node_id]
                        if isinstance(node, IfNode) and type(decision) is not bool:
                            raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='flow.condition',
                                node_id=node.condition.node_id, message='条件输出必须为严格 bool'))
                        if isinstance(node, SwitchNode) and (type(decision) is not str or decision not in branches):
                            raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='flow.router',
                                node_id=routing_node.node_id, message='路由输出不在声明的字符串枚举中'))
                        compiled, bindings = branches[decision]
                        token = execution_path.set((*execution_path.get(), node.node_id + (('.then' if decision else '.else') if isinstance(node, IfNode) else '.case[' + decision + ']')))
                        try:
                            child = await compiled.ainvoke(state.model_dump())
                        finally:
                            execution_path.reset(token)
                        value = await asyncio.to_thread(checked, catalog.contract(node.output_contract),
                            bound_value(bindings, FlowState.model_validate(child)), 'nodes.' + node.node_id + '.output')
                        return {'outputs': {**deepcopy(state.outputs), node.node_id: plain(value)},
                                'primaries': {**deepcopy(state.primaries), node.node_id: resolve(source, state)}}
                    return run
                graph.add_node(name, guarded(node.node_id, if_run(node, branches, condition_run, source, routing_node)))
                graph.add_edge(previous, name)
                previous = name
            elif isinstance(node, ForeachNode):
                child = sequence(node.body, PortReference(kind='item', node_id=node.node_id), node.item_output_contract)
                def foreach_run(node, child, source):
                    async def run(state):
                        selected = plain(resolve(node.source, state))
                        try:
                            for field in node.array_path:
                                selected = selected[field]
                        except (KeyError, TypeError):
                            raise PlatformError(ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='flow.foreach',
                                node_id=node.node_id, field_path=['arrayPath'], message='数组路径不存在')) from None
                        if type(selected) is not list:
                            raise PlatformError(ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='flow.foreach',
                                node_id=node.node_id, field_path=['arrayPath'], message='所选来源不是数组'))
                        if len(selected) > node.max_items:
                            raise PlatformError(ErrorResponse(code='LOOP_ITERATION_LIMIT', stage='flow.foreach',
                                node_id=node.node_id, field_path=['maxItems'], message='数组条数超过 maxItems，未执行任何元素'))
                        results = []
                        for index, item in enumerate(selected):
                            await boundary('node_start', node.node_id)
                            inner = state.model_copy(deep=True)
                            inner.items[node.node_id] = deepcopy(item)
                            token = execution_path.set((*execution_path.get(), f'{node.node_id}[{index}]'))
                            try:
                                updated = await child.ainvoke(inner.model_dump())
                                value = await asyncio.to_thread(checked, catalog.contract(node.item_output_contract),
                                    updated['outputs'][node.body[-1].node_id], 'nodes.' + node.node_id + '.output')
                                results.append(plain(value))
                            finally:
                                execution_path.reset(token)
                        return {'outputs': {**deepcopy(state.outputs), node.node_id: {'items': results}},
                                'primaries': {**deepcopy(state.primaries), node.node_id: resolve(source, state)}}
                    return run
                graph.add_node(name, guarded(node.node_id, foreach_run(node, child, source)))
                graph.add_edge(previous, name)
                previous = name
            else:
                child = sequence(node.body, PortReference(kind='carry', node_id=node.node_id))
                condition_graph = sequence([node.condition], PortReference(kind='carry', node_id=node.node_id)) if isinstance(node, WhileNode) else None
                def loop_run(node, child, condition_graph):
                    async def run(state):
                        contract = catalog.contract(node.carry.contract)
                        carried = await asyncio.to_thread(checked, contract, bound_value(node.carry.initial, state), 'nodes.' + node.node_id + '.input')
                        initial = plain(carried)
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
                        return {'outputs': {**deepcopy(state.outputs), node.node_id: plain(carried)},
                                'primaries': {**deepcopy(state.primaries), node.node_id: initial}}
                    return run
                graph.add_node(name, guarded(node.node_id, loop_run(node, child, condition_graph)))
                graph.add_edge(previous, name)
                previous = name
        graph.add_edge(previous, END)
        return graph.compile(checkpointer=None)

    graph = StateGraph(FlowState)
    compiled = sequence(draft.flow, PortReference(kind='input'), draft.output_contract, terminal=True)
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
