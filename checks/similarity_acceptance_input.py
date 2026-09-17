"""只验证真实验收输入准备情况，不调用模型、不代表 I8-T09/M2 完成。"""
from pathlib import Path
from agent_platform.registry.snapshots import capture

root = Path('samples/assignment-similarity')
snapshot = capture(root / 'instance')
try:
    request = snapshot.load('contracts:SimilarityInput').model_validate_json(
        (root / 'examples/acceptance-1v6.json').read_text())
    prepared = snapshot.load('preprocessing:preprocess')(request)
    assert len(prepared.comparison_paragraphs) == 6
    counts = [sum(map(len, paragraphs)) for paragraphs in [
        prepared.target_paragraphs, *prepared.comparison_paragraphs]]
    assert all(1300 <= count <= 1700 for count in counts)
    report = snapshot.load('scoring:score')(prepared)
    assert report.items[0].similarity == 1.0
    assert report.items[-1].similarity == 0.0
    print('I8-T09 输入已准备；码点数=', counts, '；确定性分值=', [item.similarity for item in report.items])
    print('未调用真实模型，不能据此宣布 I8-T09 或 M2 完成')
finally:
    snapshot.close()
