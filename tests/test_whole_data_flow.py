"""完整数据传递边界；使用真实契约、通用块和内存仓储，不调用模型。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_platform.application import create_app
from agent_platform.contracts.catalog import CatalogLoad
from agent_platform.contracts.errors import PlatformError
from agent_platform.contracts.flows import FlowDraft, PortBinding
from agent_platform.contracts.runs import RunSubmit
from agent_platform.contracts.services import ServiceWrite
from agent_platform.flows.execution import compile_flow, assemble, FlowState
from agent_platform.flows.snapshots import compile_snapshot
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

    def test_source_selection_target_rename_and_assembly_are_rejected(self):
        cases = [
            [{'target': ['text'], 'source': {'kind': 'input', 'path': ['answer']}}],
            [{'source': {'kind': 'input', 'path': ['answer']}}],
            [{'target': ['text'], 'source': {'kind': 'constant', 'value': '内容'}}],
            [{'source': {'kind': 'input'}}, {'source': {'kind': 'input'}}],
            [],
        ]
        for bindings in cases:
            with self.subTest(bindings=bindings):
                draft = self.draft()
                draft.output = [PortBinding.model_validate(value) for value in bindings]
                self.assertFalse(validate_flow(draft, self.catalog).valid)
                with self.assertRaises(PlatformError):
                    assemble(draft.output, FlowState(input={'answer': '内容'}))
        node = self.draft(converted=True)
        node.flow[0].inputs[0].source.path = ['answer']
        self.assertFalse(validate_flow(node, self.catalog).valid)

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
        raw['flow'][0]['carry']['update'][0]['target'] = ['answer']
        self.assertFalse(validate_flow(FlowDraft.model_validate(raw), self.catalog).valid)

    async def test_legacy_mapping_restores_for_editing_but_cannot_run(self):
        services = self.app.state.services
        valid = self.draft(converted=True)
        saved = services.save(ServiceWrite(name='旧服务', flow=valid))
        legacy = self.draft()
        legacy.output = [PortBinding.model_validate({
            'target': ['text'], 'source': {'kind': 'input', 'path': ['answer']}})]
        # 模拟旧编译器曾保存的合法字段映射快照，保留原始流程与摘要。
        snapshot = compile_snapshot(legacy, self.catalog, restoring=True)
        with self.assertRaises(PlatformError):
            await snapshot.graph.run({'answer': '内容'})
        store = self.app.state.store
        instance = store.read('instances')[saved.active_instance_id]
        instance['flow'] = legacy.model_dump(mode='json')
        instance['contentDigest'] = snapshot.content_digest
        document = store.read('services')[saved.service_id]
        document['service']['current']['content_digest'] = snapshot.content_digest
        document['history'][0]['content_digest'] = snapshot.content_digest
        store.write([('instances', saved.active_instance_id, instance), ('services', saved.service_id, document)])
        copied_store = MemoryStore()
        copied_store._documents = json.loads(json.dumps(store._documents))
        restored = create_app(copied_store)
        self.addCleanup(restored.state.catalog.close)
        restored_services = restored.state.services
        self.assertEqual(restored_services.schema(saved.service_id).flow.output[0].target, ['text'])
        with self.assertRaises(PlatformError):
            restored.state.submission.submit(RunSubmit(service_id=saved.service_id, input={'answer': '内容'}))
        self.assertTrue(restored.state.submission.queue.empty())
        with self.assertRaises(PlatformError):
            restored_services.activate(saved.service_id, saved.active_instance_id)
        fixed = restored_services.save(ServiceWrite(name='已转换', flow=valid), saved.service_id)
        self.assertEqual(await restored_services.resolve_current(fixed.service_id).graph.run({'answer': '内容'}), {'text': '内容'})
