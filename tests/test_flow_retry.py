"""顺序完整输入与有界重试：真实通用块、记录和预算；模型测试不访问网络。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from pydantic import ValidationError

from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.errors import ErrorResponse, PlatformError
from agent_platform.contracts.flows import FlowDraft
from agent_platform.contracts.models import ModelResponse, ModelUsage
from agent_platform.contracts.services import ServiceWrite
from agent_platform.flows.context import FlowRunContext
from agent_platform.flows.execution import compile_flow
from agent_platform.flows.validation import validate_flow
from agent_platform.runtime.boundary import Boundary, current_boundary
from agent_platform.runtime.budgets import LoopPolicy, TokenPolicy
from agent_platform.runtime.context import current_context
from agent_platform.storage import MemoryStore


class RetryChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = create_app(MemoryStore())
        self.catalog = self.app.state.catalog
        self.addCleanup(self.catalog.close)
        self.producer = self.load('producer', '''calls = 0
failures = 2
@block(id='producer',version='1.0.0',name='产生数据')
def run(value: int) -> int:
    global calls
    calls += 1
    return 'invalid' if calls <= failures else value + 1
''')
        self.consumer = self.load('consumer', '''calls = 0
@block(id='consumer',version='1.0.0',name='接收数据')
def run(value: int) -> int:
    global calls
    calls += 1
    return value * 10
''')

    def load(self, name, source):
        path = Path(self.directory.name) / (name + '.py')
        path.write_text('from agent_platform.blocks import block\n' + source)
        return self.catalog.load(CatalogLoad(kind='block', path=str(path)))

    def globals(self, resource):
        return self.catalog.artifact(resource.resource_id).entry.__globals__

    def draft(self, retry=3):
        return FlowDraft.model_validate({
            'name': '顺序重试', 'inputContract': self.producer.input_contract,
            'outputContract': self.consumer.output_contract, 'retryLimit': retry,
            'flow': [{'kind': 'block', 'nodeId': name, 'artifactRef': resource.resource_id}
                     for name, resource in [('producer', self.producer), ('consumer', self.consumer)]],
        })

    async def test_retries_only_producer_and_records_each_attempt(self):
        service = self.app.state.services.save(ServiceWrite(name='retry', flow=self.draft()))
        snapshot = self.app.state.services.resolve_current(service.service_id)
        runs = self.app.state.runs
        run = runs.create(service_id=service.service_id, instance_id=snapshot.instance_id,
                          version=service.current.version, revision=1, input=2)
        token = current_context.set(FlowRunContext(run.run_id, snapshot, runs))
        try:
            self.assertEqual(await snapshot.graph.run(2), 30)
        finally:
            current_context.reset(token)
        self.assertEqual(self.globals(self.producer)['calls'], 3)
        self.assertEqual(self.globals(self.consumer)['calls'], 1)
        steps = [s for s in runs.get(run.run_id).steps if s.step_id == 'nodes.producer' and s.kind == 'node']
        self.assertEqual([s.attempt for s in steps], [1, 2, 3])
        self.assertEqual([s.status for s in steps], ['failed', 'failed', 'completed'])

    async def test_exhaustion_and_zero_retry_never_execute_consumer(self):
        for limit in [0, 2]:
            self.globals(self.producer).update(calls=0, failures=100)
            with self.assertRaises(PlatformError) as raised:
                await compile_flow(self.draft(limit), self.catalog).run(2)
            self.assertEqual(raised.exception.error.code, 'OUTPUT_VALIDATION_ERROR')
            self.assertEqual(raised.exception.error.details.attempt, limit + 1)
            self.assertEqual(self.globals(self.producer)['calls'], limit + 1)
            self.assertEqual(self.globals(self.consumer)['calls'], 0)

    def test_retry_limit_and_declared_type_validation(self):
        self.assertEqual(self.draft(1000).retry_limit, 1000)
        for limit in [-1, 1001, 1.5, True]:
            with self.assertRaises(ValidationError):
                self.draft(limit)
        text = self.load('text', "@block(id='text',version='1.0.0',name='文本')\ndef run(value: str) -> str:\n    return value\n")
        draft = self.draft()
        draft.flow[1].artifact_ref = text.resource_id
        self.assertFalse(validate_flow(draft, self.catalog).valid)
        with self.assertRaises(PlatformError):
            self.app.state.services.save(ServiceWrite(name='bad', flow=draft))
        self.assertEqual(self.globals(self.producer)['calls'], 0)

    async def test_initial_input_and_non_contract_errors_are_not_retried(self):
        with self.assertRaises(PlatformError):
            await compile_flow(self.draft(), self.catalog).run('wrong')
        self.assertEqual(self.globals(self.producer)['calls'], 0)
        failure = self.load('failure', '''from agent_platform.contracts.errors import ErrorResponse, PlatformError
calls = 0
error_code = 'API_TRANSPORT_ERROR'
error_stage = 'api.transport'
@block(id='failure',version='1.0.0',name='外部错误')
def run(value: int) -> int:
    global calls
    calls += 1
    raise PlatformError(ErrorResponse(code=error_code,stage=error_stage,message='失败'))
''')
        draft = self.draft()
        draft.flow[0].artifact_ref = failure.resource_id
        for code, stage in [('API_TRANSPORT_ERROR', 'api.transport'), ('OUTPUT_VALIDATION_ERROR', 'model.usage')]:
            self.globals(failure).update(calls=0, error_code=code, error_stage=stage)
            with self.assertRaises(PlatformError) as raised:
                await compile_flow(draft, self.catalog).run(2)
            self.assertEqual(raised.exception.error.code, code)
            self.assertEqual(self.globals(failure)['calls'], 1)

    async def test_cancel_between_attempts_stops_retry(self):
        def cancel(phase, node):
            if phase == 'node_start' and node == 'producer' and self.globals(self.producer)['calls']:
                raise PlatformError(ErrorResponse(code='RUN_CANCELLED',stage='run',message='取消'))
        token = current_boundary.set(Boundary(observer=cancel))
        try:
            with self.assertRaises(PlatformError) as raised:
                await compile_flow(self.draft(), self.catalog).run(2)
            self.assertEqual(raised.exception.error.code, 'RUN_CANCELLED')
        finally:
            current_boundary.reset(token)
        self.assertEqual(self.globals(self.producer)['calls'], 1)
        self.assertEqual(self.globals(self.consumer)['calls'], 0)

    async def test_package_retries_charge_loop_and_token_budgets(self):
        resource = self.catalog.load(CatalogLoad(kind='package', path='samples/packages/minimal'))
        env = self.app.state.environments.save(EnvironmentWrite(name='model', connections=[{
            'kind': 'model', 'connectionId': 'model', 'baseUrl': 'http://127.0.0.1:1', 'model': 'test',
        }]))
        class Model:
            calls = 0
            async def invoke(self, connection, request):
                self.calls += 1
                return ModelResponse(output={'wrong': 'value'} if self.calls < 3 else {'text': 'ok'},
                                     usage=ModelUsage(input_tokens=2, output_tokens=1, quality='exact', source='test'))
        for limit in [4, 1]:
            draft = FlowDraft.model_validate({
                'name': 'package', 'inputContract': resource.input_contract, 'outputContract': resource.output_contract,
                'retryLimit': 3, 'budget': {'loopLimit': limit, 'tokenLimit': 100},
                'flow': [{'kind': 'package', 'nodeId': 'chat', 'artifactRef': resource.resource_id}],
                'nodeConfigurations': {'chat': {'parameters': {}, 'model': {'environmentId': env.environment_id, 'connectionId': 'model'},
                    'budget': {'loopLimit': limit, 'tokenLimit': 100}, 'maxOutputTokens': 20}},
            })
            service = self.app.state.services.save(ServiceWrite(name='package', flow=draft))
            snapshot = self.app.state.services.resolve_current(service.service_id)
            runs = self.app.state.runs
            run = runs.create(service_id=service.service_id, instance_id=snapshot.instance_id,
                              version=service.current.version, revision=1, input={'text': 'input'}, environment_snapshot=[env])
            model = Model()
            token_policy = TokenPolicy(run.run_id, snapshot, runs)
            ct = current_context.set(FlowRunContext(run.run_id, snapshot, runs, model, token_policy))
            bt = current_boundary.set(Boundary(policies=[LoopPolicy(run.run_id, snapshot, runs), token_policy]))
            try:
                if limit == 1:
                    with self.assertRaises(PlatformError) as raised:
                        await snapshot.graph.run({'text': 'input'})
                    self.assertEqual(raised.exception.error.code, 'LOOP_BUDGET_EXCEEDED')
                else:
                    self.assertEqual(await snapshot.graph.run({'text': 'input'}), {'text': 'ok'})
            finally:
                current_context.reset(ct)
                current_boundary.reset(bt)
            expected_calls = 1 if limit == 1 else 3
            self.assertEqual(model.calls, expected_calls)
            usage = runs.get(run.run_id).usage
            self.assertEqual(usage['loops']['global'], expected_calls)
            self.assertEqual(usage['tokens']['global']['totalTokens'], expected_calls * 3)

    async def test_downstream_input_rejection_reinvokes_only_previous_node(self):
        self.globals(self.producer)['failures'] = 0
        adapter = self.catalog.contract(self.consumer.input_contract).adapter
        validate = adapter.validate_python
        checks = 0
        def reject_twice(value, **kwargs):
            nonlocal checks
            checks += 1
            if checks <= 2:
                validate('invalid', strict=True)
            return validate(value, **kwargs)
        graph = compile_flow(self.draft(2), self.catalog)
        with patch.object(adapter, 'validate_python', side_effect=reject_twice):
            self.assertEqual(await graph.run(2), 30)
        self.assertEqual(self.globals(self.producer)['calls'], 3)
        self.assertEqual(self.globals(self.consumer)['calls'], 1)

    def test_service_persists_retry_limit_as_versioned_configuration(self):
        services = self.app.state.services
        first = services.save(ServiceWrite(name='retry', flow=self.draft(0)))
        second = services.save(ServiceWrite(name='retry', flow=self.draft(1000)), first.service_id)
        self.assertEqual(second.current.change_kind, 'minor')
        self.assertEqual(services.resolve_current(first.service_id).draft.retry_limit, 1000)
        self.assertEqual(services.snapshots.get(first.active_instance_id).draft.retry_limit, 0)

    async def test_while_condition_and_body_receive_current_carry(self):
        condition = self.load('condition', "@block(id='condition',version='1.0.0',name='判断')\ndef run(value: int) -> bool:\n    return value < 3\n")
        raw = self.draft().model_dump(by_alias=True)
        raw['outputContract'] = self.producer.output_contract
        raw['flow'] = [{'kind': 'while', 'nodeId': 'loop', 'maxIterations': 3,
            'condition': {'kind': 'block', 'nodeId': 'check', 'artifactRef': condition.resource_id},
            'carry': {'contract': self.producer.input_contract,
                      'initial': [{'source': {'kind': 'input'}}],
                      'update': [{'source': {'kind': 'node', 'nodeId': 'producer'}}]},
            'body': [{'kind': 'block', 'nodeId': 'producer', 'artifactRef': self.producer.resource_id}]}]
        self.assertEqual(await compile_flow(FlowDraft.model_validate(raw), self.catalog).run(0), 3)
        self.assertEqual(self.globals(self.producer)['calls'], 5)
