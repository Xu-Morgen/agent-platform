from pathlib import Path
import argparse
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from agent_platform.registry.snapshots import capture


def docx_text(path):
    """只为本地测验提取 Word 正文；不读取表格报告、不推断 AI/抄袭标签。"""
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    return '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t', ns))
        for p in root.findall('.//w:p', ns))


def main(artifact_dir=None):
    snapshot = capture('samples/assignment-similarity/instance')
    Input = snapshot.load('contracts:SimilarityInput')
    preprocess = snapshot.load('preprocessing:preprocess')
    score = snapshot.load('scoring:score')
    def run(target, comparisons):
        return score(preprocess(Input(target_text=target, comparison_texts=comparisons)))
    report = run('甲乙\n丙丁', ['甲乙\n丙丁', '无关', '甲乙', '甲乙\n甲乙'])
    assert [item.similarity for item in report.items] == [1.0, 0.0, 0.5, 0.5]
    assert report.items[3].matches[0].comparison_paragraph_indices == [0, 1]
    repeated = run('甲乙\n甲乙\n丙丁', ['甲乙']).items[0]
    assert (repeated.matched_target_characters, repeated.total_target_characters) == (4, 6)
    assert [m.target_paragraph_index for m in repeated.matches] == [0, 1]
    unicode = run('e\u0301😀\n甲乙', ['é😀']).items[0]
    assert (unicode.matched_target_characters, unicode.total_target_characters) == (2, 4)
    if artifact_dir:
        paths = sorted(Path(artifact_dir).rglob('*.docx'))
        assert len(paths) >= 7, 'artifact 需要至少 7 篇 DOCX'
        texts = [docx_text(path) for path in paths[:7]]
        actual = run(texts[0], texts[1:])
        assert len(actual.items) == 6
        assert run(texts[0], [texts[0]]).items[0].similarity == 1
        print('artifact DOCX 本地 1 对 6：字符数=', [len(t) for t in texts],
              '段落完全匹配分值=', [i.similarity for i in actual.items])
    snapshot.close()
    print('I5-T03：1/0/0.5、对照重复不放大、目标重复按位置、Unicode 码点与索引通过')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-dir')
    main(parser.parse_args().artifact_dir)
