"""从权威契约同步源码和 Schema；不加载资源、绑定连接或创建服务。"""
import argparse
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parent
BEGIN = '# BEGIN GENERATED CONTRACTS\n'
END = '# END GENERATED CONTRACTS\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = (ROOT / 'quality_contracts.py').read_text()
    mismatches = []
    for path in sorted(ROOT.glob('*/models.py')) + sorted((ROOT / 'quality-blocks').glob('*.py')):
        text = path.read_text()
        head, tail = text.split(BEGIN, 1)
        _, tail = tail.split(END, 1)
        expected = head + BEGIN + source + END + tail
        if text != expected:
            mismatches.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(expected)
    namespace = runpy.run_path(str(ROOT / 'quality_contracts.py'))
    examples = json.loads((ROOT / 'contract-examples.json').read_text())
    for key, name in [('document', 'Document'), ('planning', 'Planning'),
                      ('questions', 'GeneratedQuestions'), ('review', 'ReviewResult')]:
        namespace[name].model_validate(examples[key])
    schemas = {name: namespace[name].model_json_schema(by_alias=True) for name in (
        'Document', 'Planning', 'SufficientPlan', 'GeneratedQuestions', 'ReviewResult', 'QuestionState',
        'PlannerEntry', 'GeneratorEntry', 'StateEntry')}
    path = ROOT / 'quality-schemas.json'
    expected = json.dumps(schemas, ensure_ascii=False, indent=2) + '\n'
    if not path.exists() or path.read_text() != expected:
        mismatches.append(path.name)
        if not args.check:
            path.write_text(expected)
    if args.check and mismatches:
        raise SystemExit('契约未同步：' + ', '.join(mismatches))
    print('契约与 Schema 已同步' if not args.check else '契约与 Schema 一致')


if __name__ == '__main__':
    main()
