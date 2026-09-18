"""完整数据传递边界；使用真实契约、通用块和内存仓储，不调用模型。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from pydantic import ValidationError

from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.errors import PlatformError
from agent_platform.contracts.flows import FlowDraft, PortBinding, ModuleNode
from agent_platform.contracts.services import ServiceWrite
from agent_platform.flows.execution import compile_flow, bound_value, FlowState
from agent_platform.flows.validation import validate_flow
from agent_platform.storage import MemoryStore


class WholeDataChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        source = Path(self.directory.name) / 'convert.py'
        source.write_text('''from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel
class Answer(StrictModel):
    answer: str
class Text(StrictModel):
    text: str
@block(id='answer-to-text', version='1.0.0', name='字段转换')
def convert(value: Answer) -> Text:
    return Text(text=value.answer)
''')
        self.app = create_app(MemoryStore())
        self.catalog = self.app.state.catalog
        self.addCleanup(self.catalog.close)
        self.resource = self.catalog.load(CatalogLoad(kind='block', path=str(source)))
        source = Path(self.directory.name) / 'produce.py'
        source.write_text('''from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel
class Answer(StrictModel):
    answer: str
@block(id='produce-answer', version='1.0.0', name='产生结果')
def produce(value: Answer) -> Answer:
    return Answer(answer=value.answer + '!')
''')
        self.producer = self.catalog.load(CatalogLoad(kind='block', path=str(source)))

    def draft(self, *, converted=False):
        resource = self.resource
        return FlowDraft.model_validate({
            'name': '返回结果', 'inputContract': resource.input_contract,
            'outputContract': resource.output_contract,
            'flow': [{'kind': 'block', 'nodeId': 'produce', 'artifactRef': self.producer.resource_id}] + ([
                {'kind': 'block', 'nodeId': 'convert', 'artifactRef': resource.resource_id}] if converted else []),
        })

    async def test_mismatched_fields_require_real_conversion_block(self):
        invalid = self.draft()
        result = validate_flow(invalid, self.catalog)
        self.assertFalse(result.valid)
        self.assertIn('text', result.issues[0].reason)
        self.assertIn('通用块', result.issues[0].reason)
        with self.assertRaises(PlatformError):
            self.app.state.services.save(ServiceWrite(name='不兼容', flow=invalid))
        valid = self.draft(converted=True)
        self.assertTrue(validate_flow(valid, self.catalog).valid)
        self.assertEqual(await compile_flow(valid, self.catalog).run({'answer': '实际内容'}), {'text': '实际内容!'})

    def test_field_mapping_is_not_part_of_the_protocol(self):
        for binding in [
            {'target': [], 'source': {'kind': 'input'}},
            {'target': ['text'], 'source': {'kind': 'input'}},
            {'source': {'kind': 'input', 'path': []}},
            {'source': {'kind': 'input', 'path': ['answer']}},
        ]:
            with self.subTest(binding=binding), self.assertRaises(ValidationError):
                PortBinding.model_validate(binding)

    def test_modules_cannot_choose_inputs(self):
        raw = self.draft().flow[0].model_dump(by_alias=True)
        raw['inputs'] = [{'source': {'kind': 'input'}}]
        with self.assertRaises(ValidationError):
            ModuleNode.model_validate(raw)
        draft = self.draft(converted=True)
        draft.flow.reverse()
        result = validate_flow(draft, self.catalog)
        self.assertFalse(result.valid)
        self.assertTrue(any(issue.node_id == 'produce' for issue in result.issues))

    def test_control_values_require_exactly_one_source(self):
        for sources in [[], [{'source': {'kind': 'input'}}] * 2]:
            with self.subTest(sources=sources), self.assertRaises(PlatformError):
                bound_value([PortBinding.model_validate(source) for source in sources], FlowState(input={'answer': '内容'}))

    def test_complete_constants_and_loop_data_are_validated(self):
        raw = self.draft().model_dump(by_alias=True)
        raw['outputContract'] = self.resource.input_contract
        raw['flow'] = [{'kind': 'repeat', 'nodeId': 'repeat', 'count': 1, 'body': [], 'carry': {
            'contract': self.resource.input_contract,
            'initial': [{'source': {'kind': 'input'}}],
            'update': [{'source': {'kind': 'carry', 'nodeId': 'repeat'}}],
        }}]
        self.assertTrue(validate_flow(FlowDraft.model_validate(raw), self.catalog).valid)
        raw['flow'][0]['carry']['initial'] = [{'source': {'kind': 'constant', 'value': {'answer': '固定内容'}}}]
        self.assertTrue(validate_flow(FlowDraft.model_validate(raw), self.catalog).valid)
        raw['flow'][0]['carry']['initial'][0]['source']['value'] = {'other': '错误字段'}
        self.assertFalse(validate_flow(FlowDraft.model_validate(raw), self.catalog).valid)
        raw['flow'][0]['carry']['update'] = []
        self.assertFalse(validate_flow(FlowDraft.model_validate(raw), self.catalog).valid)

    def test_return_source_is_not_configurable_and_empty_flow_is_invalid(self):
        raw = self.draft(converted=True).model_dump(by_alias=True)
        raw['output'] = [{'source': {'kind': 'input'}}]
        with self.assertRaises(ValidationError):
            FlowDraft.model_validate(raw)
        draft = self.draft()
        draft.flow = []
        self.assertFalse(validate_flow(draft, self.catalog).valid)
        with self.assertRaises(PlatformError):
            compile_flow(draft, self.catalog)

    async def test_final_loop_returns_its_complete_output(self):
        draft = self.draft()
        raw = draft.model_dump(by_alias=True)
        raw['outputContract'] = self.producer.output_contract
        raw['flow'] = [{'kind': 'repeat', 'nodeId': 'repeat', 'count': 2,
            'carry': {'contract': self.producer.input_contract,
                      'initial': [{'source': {'kind': 'input'}}],
                      'update': [{'source': {'kind': 'node', 'nodeId': 'produce'}}]},
            'body': [{'kind': 'block', 'nodeId': 'produce', 'artifactRef': self.producer.resource_id}]}]
        result = await compile_flow(FlowDraft.model_validate(raw), self.catalog).run({'answer': '循环'})
        self.assertEqual(result, {'answer': '循环!!'})

    async def test_final_branch_returns_selected_branch_output(self):
        path = Path(self.directory.name) / 'condition.py'
        path.write_text("from agent_platform.blocks import block\n@block(id='condition',version='1.0.0',name='判断')\ndef condition(value: bool) -> bool:\n    return value\n")
        condition = self.catalog.load(CatalogLoad(kind='block', path=str(path)))
        for decision, expected in [(True, '成立'), (False, '否则')]:
            raw = self.draft().model_dump(by_alias=True)
            raw['inputContract'] = condition.input_contract
            raw['outputContract'] = self.resource.output_contract
            raw['flow'] = [
                {'kind': 'block', 'nodeId': 'condition', 'artifactRef': condition.resource_id},
                {'kind': 'if', 'nodeId': 'branch', 'condition': {'kind': 'node', 'nodeId': 'condition'},
                 'outputContract': self.resource.output_contract,
                 'thenBranch': {'nodes': [], 'output': [{'source': {'kind': 'constant', 'value': {'text': '成立'}}}]},
                 'elseBranch': {'nodes': [], 'output': [{'source': {'kind': 'constant', 'value': {'text': '否则'}}}]}},
            ]
            result = await compile_flow(FlowDraft.model_validate(raw), self.catalog).run(decision)
            self.assertEqual(result, {'text': expected})
