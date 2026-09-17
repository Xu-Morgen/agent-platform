"""报告仅为人工构造的契约样例，不冒充计分或模型执行。"""
from copy import deepcopy
import json
from pathlib import Path
from pydantic import ValidationError
from agent_platform.registry.snapshots import capture

ROOT = Path('samples/assignment-similarity')


def rejected(operation):
    try:
        operation()
    except ValidationError:
        return
    raise AssertionError('非法数据未被拒绝')


def main():
    snapshot = capture(ROOT / 'instance')
    Input = snapshot.load('contracts:SimilarityInput')
    validate = snapshot.load('contracts:validate_report')
    request = Input.model_validate_json((ROOT / 'examples/input.json').read_text())
    report = json.loads((ROOT / 'examples/report-contract.json').read_text())
    assert validate(report, request).quantitative.items[0].similarity == 0.5
    for payload in ({'targetText':'a','comparisonTexts':[]},
                    {'targetText':'a','comparisonTexts':[2]},
                    {'targetText':2,'comparisonTexts':['a']},
                    {'targetText':'a','comparisonTexts':['a'],'extra':True}):
        rejected(lambda: Input.model_validate(payload))
    for path, value in [
        (('quantitative','items'), []),
        (('qualitative','items'), []),
        (('quantitative','items',0,'similarity'), 1.1),
        (('quantitative','items',0,'similarity'), float('nan')),
        (('quantitative','items',0,'similarity'), '0.5'),
        (('quantitative','items',0,'matchedTargetCharacters'), 5),
        (('quantitative','items',0,'totalTargetCharacters'), 0),
        (('quantitative','items',0,'comparisonIndex'), -1),
        (('qualitative','items',1,'comparisonIndex'), 0),
        (('qualitative','items',1,'comparisonIndex'), 2),
        (('qualitative','items',0,'reason'), 2),
        (('qualitative','items',0,'relation'), True),
        (('quantitative','items',0,'matches',0,'comparisonParagraphIndices'), [0,0]),
    ]:
        bad = deepcopy(report)
        cursor = bad
        for part in path[:-1]:
            cursor = cursor[part]
        cursor[path[-1]] = value
        rejected(lambda: validate(bad, request))
    bad = deepcopy(report)
    for kind in ('quantitative','qualitative'):
        bad[kind]['items'].pop()
    rejected(lambda: validate(bad, request))
    snapshot.close()
    print('I5-T01：合法报告、严格类型、数值边界、重复/缺失/越界索引通过')


if __name__ == '__main__':
    main()
