from pydantic import ValidationError
from agent_platform.contracts import StrictModel, export_schema

class Child(StrictModel):
    item_count: int

class Parent(StrictModel):
    child: Child

assert Parent.model_validate({'child': {'itemCount': 2}}).child.item_count == 2
for data, path in [
    ({'child': {'itemCount': '2'}}, ('child', 'itemCount')),
    ({'child': {'itemCount': 2, 'other': True}}, ('child', 'other')),
    ({'child': {'itemCount': 2}, 'other': True}, ('other',)),
]:
    try:
        Parent.model_validate(data)
    except ValidationError as e:
        assert e.errors()[0]['loc'] == path
    else:
        raise AssertionError(data)
schema = export_schema(Parent)
assert schema['additionalProperties'] is False
assert schema['$defs']['Child']['additionalProperties'] is False
assert schema['$defs']['Child']['properties']['itemCount']['type'] == 'integer'
print('T03 PASS: nested strict validation and same-model Schema')
