"""完整数据传递边界；使用真实契约、通用块和内存仓储，不调用模型。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from pydantic import ValidationError

from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.errors import PlatformError
from agent_platform.contracts.flows import FlowDraft, PortBinding
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

    def draft(self, *, converted=False):
        resource = self.resource
        return FlowDraft.model_validate({
            'name': '返回结果', 'inputContract': resource.input_contract,
            'outputContract': resource.output_contract,
            'flow': [{'kind': 'block', 'nodeId': 'convert', 'artifactRef': resource.resource_id,
                      'inputs': [{'source': {'kind': 'input'}}]}] if converted else [],
            'output': [{'source': {'kind': 'node', 'nodeId': 'convert'} if converted else {'kind': 'input'}}],
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
        self.assertEqual(await compile_flow(valid, self.catalog).run({'answer': '实际内容'}), {'text': '实际内容'})

    def test_field_mapping_is_not_part_of_the_protocol(self):
        for binding in [
            {'target': [], 'source': {'kind': 'input'}},
            {'target': ['text'], 'source': {'kind': 'input'}},
            {'source': {'kind': 'input', 'path': []}},
            {'source': {'kind': 'input', 'path': ['answer']}},
        ]:
            with self.subTest(binding=binding), self.assertRaises(ValidationError):
                PortBinding.model_validate(binding)

    def test_exactly_one_complete_source_is_required(self):
        for sources in [[], [{'source': {'kind': 'input'}}] * 2]:
            with self.subTest(sources=sources):
                draft = self.draft()
                draft.output = [PortBinding.model_validate(source) for source in sources]
                self.assertFalse(validate_flow(draft, self.catalog).valid)
                with self.assertRaises(PlatformError):
                    bound_value(draft.output, FlowState(input={'answer': '内容'}))

    def test_complete_constants_and_loop_data_are_validated(self):
        draft = self.draft()
        draft.output = [PortBinding.model_validate({'source': {'kind': 'constant', 'value': {'text': '固定内容'}}})]
        self.assertTrue(validate_flow(draft, self.catalog).valid)
        draft.output[0].source.value = {'answer': '错误字段'}
        self.assertFalse(validate_flow(draft, self.catalog).valid)
        raw = self.draft().model_dump(by_alias=True)
        raw['outputContract'] = self.resource.input_contract
        raw['flow'] = [{'kind': 'repeat', 'nodeId': 'repeat', 'count': 1, 'body': [], 'carry': {
            'contract': self.resource.input_contract,
            'initial': [{'source': {'kind': 'input'}}],
            'update': [{'source': {'kind': 'carry', 'nodeId': 'repeat'}}],
        }}]
        raw['output'] = [{'source': {'kind': 'node', 'nodeId': 'repeat'}}]
        self.assertTrue(validate_flow(FlowDraft.model_validate(raw), self.catalog).valid)
        raw['flow'][0]['carry']['update'] = []
        self.assertFalse(validate_flow(FlowDraft.model_validate(raw), self.catalog).valid)
