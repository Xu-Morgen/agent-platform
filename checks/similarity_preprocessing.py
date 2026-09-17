from agent_platform.registry.snapshots import capture
from agent_platform.contracts.errors import PlatformError

snapshot = capture('samples/assignment-similarity/instance')
Input = snapshot.load('contracts:SimilarityInput')
preprocess = snapshot.load('preprocessing:preprocess')
result = preprocess(Input(target_text='  Cafe\u0301\t A! \r\n\r\n 乙\u3000\u3000丙。\rD? ', comparison_texts=['Cafe\u0301 A!\n\n']))
assert result.target_paragraphs == ['Café A!', '乙 丙。', 'D?']
assert result.comparison_paragraphs == [['Café A!']]
for target, comparisons, path in [
    (' \t\r\n', ['a'], ['targetText']),
    ('a', ['a', '\t\u3000\n'], ['comparisonTexts', 1]),
]:
    try:
        preprocess(Input(target_text=target, comparison_texts=comparisons))
    except PlatformError as exc:
        assert exc.error.field_path == path
    else:
        raise AssertionError('空白文本应拒绝')
snapshot.close()
print('I5-T02：固定段落、NFC/换行/水平空白规范、大小写标点保留及原字段路径通过')
