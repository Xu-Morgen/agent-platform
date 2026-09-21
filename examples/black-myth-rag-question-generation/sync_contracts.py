"""同步单一契约源到自包含资源；不加载资源或创建服务。"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BEGIN = '# BEGIN GENERATED CONTRACTS\n'
END = '# END GENERATED CONTRACTS\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = (ROOT / 'contracts.py').read_text()
    changed = []
    for path in sorted(ROOT.glob('*/models.py')) + sorted((ROOT / 'blocks').glob('*.py')):
        head, rest = path.read_text().split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        expected = head + BEGIN + source + END + tail
        if path.read_text() != expected:
            changed.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(expected)
    if args.check and changed:
        raise SystemExit('契约副本未同步：' + ', '.join(changed))
    print('契约副本一致' if args.check else '契约已同步')


if __name__ == '__main__':
    main()
