from pathlib import Path
from agent_platform.contracts.control import parse_control
for path in Path('examples/control').glob('*.json'):
    message = parse_control(path.read_text())
    assert message.protocol_version == 1
for data in ['{"protocolVersion":1,"type":"unknown"}', '{"type":"ready","address":"http://127.0.0.1:8000"}', '{"protocolVersion":true,"type":"shutdown"}']:
    try:
        parse_control(data)
    except ValueError:
        pass
    else:
        raise AssertionError(data)
print('T06 PASS: three message examples, unknown type and bad version rejected')
