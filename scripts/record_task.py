"""回填单卡验收记录并同步索引。"""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('number', type=int)
parser.add_argument('files')
parser.add_argument('verification')
parser.add_argument('decision')
args = parser.parse_args()
key = f'I1-T{args.number:02}'
p = Path('docs/tasks/i1.md')
s = p.read_text()
start = s.index(f'## {key} ')
end = s.find('<a id=', start)
if end < 0:
    end = len(s)
card = s[start:end]
card = card[:card.index('- **交接记录**')] + f'''- **交接记录**：
  - 状态：完成。
  - 实际文件：{args.files}。
  - 验证：{args.verification}。
  - 使用环境：Python 3.12.3、项目 `.venv` 与 `uv.lock`；桌面依赖见 `desktop/package-lock.json`；均为本地运行，不涉及真实模型。
  - 未完成与阻塞：无；仅完成本卡范围。
  - 实现决定：{args.decision}。
  - 下一可执行任务：按索引中显式依赖选择未完成卡。

'''
s = s[:start] + card + s[end:]
completed = s.count('状态：完成。')
lines = s.splitlines()
lines[2] = f'- 状态：已完成 {completed}/13 张任务卡；详细状态及证据见各卡交接记录。'
p.write_text('\n'.join(lines).rstrip() + '\n')
p = Path('docs/iteration-plan.md')
s = p.read_text()
lines = s.splitlines()
for i, line in enumerate(lines):
    if line.startswith('- 状态：'):
        lines[i] = f'- 状态：I1 已完成 {completed}/13 张；后续阶段未开始'
    if line.startswith(f'| [{key}]'):
        lines[i] = line.rsplit('|', 2)[0] + '| 完成 |'
p.write_text('\n'.join(lines).rstrip() + '\n')
