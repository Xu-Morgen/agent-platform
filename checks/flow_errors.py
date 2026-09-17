from pydantic import ValidationError, field_validator
from agent_platform.contracts.base import StrictModel, export_schema
from agent_platform.contracts.errors import ErrorResponse, PlatformError
from agent_platform.runtime.validation import validate
from agent_platform.validation_issues import validation_exception
from agent_platform.contracts.flows import FlowDraft
from flow_ports import fixture
import json
from pathlib import Path

class Input(StrictModel):
    text: str

try:
    validate(Input, {'text': 23}, 'block.input')
except PlatformError as exc:
    assert '字符串' in exc.error.message and exc.error.issues[0].field_path == ['text']
else: raise AssertionError()

class Secret(StrictModel):
    text: str
    @field_validator('text')
    @classmethod
    def fail(cls, value):
        raise ValueError('Authorization Bearer ' + value)

try:
    Secret(text='synthetic-secret-student-text')
except ValidationError as exc:
    error = validation_exception(exc).error
    assert 'synthetic-secret' not in error.model_dump_json() and 'Authorization' not in error.model_dump_json()

catalog, draft = fixture()
draft['flow'][1]['nodeId'] = 'convert'
try:
    FlowDraft.model_validate(draft)
except ValidationError as exc:
    error = validation_exception(exc).error
    assert '重复' in error.message and error.field_path[-1] == 'nodeId'

# 已有业务自定义重复索引原因必须保留，输入内容不能透出。
from agent_platform.registry.snapshots import capture
snapshot = capture('samples/assignment-similarity/packages/semantic')
try:
    validate(snapshot.load('contracts:ParagraphMatch'),
             {'targetParagraphIndex': 0, 'comparisonParagraphIndices': [1, 1]}, 'package.output')
except PlatformError as exc:
    assert exc.error.message == '对照段落索引不得重复'
else:
    raise AssertionError('重复索引未拒绝')
try:
    validate(Input, {}, 'block.input')
except PlatformError as exc:
    assert exc.error.message == '缺少必填字段'
Path('desktop/contracts/error.schema.json').write_text(json.dumps(export_schema(ErrorResponse), ensure_ascii=False, indent=2) + '\n')
print('flow errors: OK (具体类型、重复原因、字段位置、自定义异常与输入脱敏、桌面 Schema 同步)')
