"""从 Python 权威模型生成桌面所需 Schema；无需额外 npm 校验依赖。"""
import json
from pathlib import Path
from agent_platform.contracts import export_schema
from agent_platform.contracts.control import CONTROL
from agent_platform.contracts.health import HealthResponse
from agent_platform.contracts.errors import ErrorResponse

schemas = {'control': CONTROL.json_schema(by_alias=True), 'health': export_schema(HealthResponse), 'error': export_schema(ErrorResponse)}
# 线路协议要求版本和类型显式出现，而构造 Python 消息允许使用常量默认值。
for name in ('Ready', 'StartupError', 'Shutdown'):
    schema = schemas['control']['$defs'][name]
    schema['required'] = list(dict.fromkeys([*schema.get('required', []), 'protocolVersion', 'type']))
for name, schema in schemas.items():
    Path(f'desktop/contracts/{name}.schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2) + '\n')
