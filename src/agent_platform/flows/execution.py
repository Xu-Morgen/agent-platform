"""显式端口编译器：图状态只存已校验的值，模块只接收自己的输入。"""
from copy import deepcopy
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any
from pydantic import BaseModel, Field, ValidationError
from langgraph.graph import START, END, StateGraph
from langgraph.errors import GraphRecursionError
from ..contracts.base import StrictModel
from ..contracts.flows import FlowDraft, ModuleNode, ConstantValue
from ..contracts.errors import PlatformError, ErrorResponse
from ..runtime.context import current_context
from ..runtime.boundary import checkpoint
from .validation import validate_flow

COMPILER_VERSION = 'flow-1'


def plain(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode='json', by_alias=True)
    return deepcopy(value)


def checked(contract, value, stage):
    try:
        return contract.adapter.validate_python(plain(value), strict=True)
    except ValidationError as exc:
        from ..validation_issues import validation_exception
        raise validation_exception(exc, stage=stage,
            code='OUTPUT_VALIDATION_ERROR' if stage.endswith('output') else 'CONTRACT_VALIDATION_ERROR') from None


def resolve(source, state):
    if isinstance(source, ConstantValue):
        return deepcopy(source.value)
    value = state.input if source.kind == 'input' else state.outputs[source.node_id]
    for key in source.path:
        value = value[key]
    return deepcopy(value)


def assemble(bindings, state):
    result = {}
    for binding in bindings:
        value = resolve(binding.source, state)
        if not binding.target:
            return value
        target = result
        for key in binding.target[:-1]:
            target = target.setdefault(key, {})
        target[binding.target[-1]] = value
    return result


class FlowState(StrictModel):
    input: Any
    outputs: dict[str, Any] = Field(default_factory=dict)
    result: Any = None


@dataclass(frozen=True)
class FlowExecutor:
    draft: FlowDraft
    catalog: object
    graph: object

    async def run(self, value, *, recursion_limit=10000):
        value = checked(self.catalog.contract(self.draft.input_contract), value, 'flow.input')
        try:
            result = await self.graph.ainvoke({'input': plain(value)}, config={'recursion_limit': recursion_limit})
            return deepcopy(result['result'])
        except GraphRecursionError:
            raise PlatformError(ErrorResponse(code='GRAPH_EXECUTION_LIMIT', stage='flow', message='图执行步数超过限制')) from None


def compile_flow(draft, catalog):
    draft = draft.model_copy(deep=True)
    validation = validate_flow(draft, catalog)
    if not validation.valid:
        raise PlatformError(ErrorResponse(code='CONTRACT_VALIDATION_ERROR', stage='flow.compile',
            message='拼图端口校验失败', issues=validation.issues))
    graph = StateGraph(FlowState)

    def wrap(node):
        async def execute(state):
            stage = 'nodes.' + node.node_id
            try:
                view = catalog.get(node.artifact_ref)
                value = checked(catalog.contract(view.input_contract), assemble(node.inputs, state), stage + '.input')
                context = current_context.get()
                if node.kind == 'block':
                    operation = lambda: catalog.artifact(node.artifact_ref).invoke(plain(value))
                    result = await context.run_step(stage, operation, kind='block') if context else await operation()
                else:
                    if context is None:
                        raise PlatformError(ErrorResponse(code='DEPENDENCY_ERROR', stage=stage, message='包执行需要任务上下文'))
                    result = await context.invoke_package(node.node_id, plain(value))
                result = checked(catalog.contract(view.output_contract), result, stage + '.output')
                return {'outputs': {**deepcopy(state.outputs), node.node_id: plain(result)}}
            except PlatformError as exc:
                exc.error.node_id = node.node_id
                raise
        return execute

    previous = START
    for index, node in enumerate(draft.flow):
        if not isinstance(node, ModuleNode):
            raise PlatformError(ErrorResponse(code='CONFIGURATION_ERROR', stage='flow.compile', message='当前编译器仅支持顺序节点'))
        name = f'module_{index}'
        graph.add_node(name, wrap(node), retry_policy=None)
        graph.add_edge(previous, name)
        previous = name

    async def output(state):
        result = checked(catalog.contract(draft.output_contract), assemble(draft.output, state), 'flow.output')
        return {'result': plain(result)}

    graph.add_node('output', output)
    graph.add_edge(previous, 'output')
    graph.add_edge('output', END)
    return FlowExecutor(draft, catalog, graph.compile(checkpointer=None))
