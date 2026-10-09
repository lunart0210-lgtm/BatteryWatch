"""Пробой 10-дневного минимума: красный только при пробое на LOW_BREAK_RED %
и больше, мелкий пробой — жёлтый.

Запуск:  cd /opt/stocks && venv/bin/python patch_lowbreak.py
Делает бэкап stocks.py.bak-<время>, при ошибке синтаксиса откатывается.
"""
import pathlib
import py_compile
import re
import shutil
import sys
import time

TARGET = pathlib.Path(__file__).resolve().parent / 'stocks.py'
src = TARGET.read_text()
if 'broke_low_deep' in src:
    sys.exit('уже применено, изменений нет')
lines = src.split('\n')


def one(pred, what):
    idx = [i for i, l in enumerate(lines) if pred(l)]
    if len(idx) != 1:
        sys.exit('не нашёл ровно одну строку «%s» (%d) — ничего не менял' % (what, len(idx)))
    return idx[0]


const = one(lambda l: re.match(r'YELLOW_DROP\s*=', l), 'YELLOW_DROP =')
quote = one(lambda l: 'low10=low10' in l and 'broke_low=broke_low,' in l, 'low10=low10, broke_low=broke_low,')
red = one(lambda l: "return 'red'" in l and "q['change_pct']<=RED_DROP" in l, "return 'red'")
yellow = one(lambda l: "q['change_pct']<=YELLOW_DROP:" in l and "return 'yellow'" in l, "return 'yellow'")
changed = [quote, red, yellow]

lines[quote] = lines[quote].replace(
    'broke_low=broke_low,',
    'broke_low=broke_low, broke_low_deep=(low10 is not None and price<low10*(1-LOW_BREAK_RED/100)),', 1)
if "q['broke_low']" in lines[red]:
    lines[red] = lines[red].replace("q['broke_low']", "q.get('broke_low_deep')", 1)
else:  # если уже стоял вариант «пробой = жёлтый»
    lines[red] = lines[red].replace("q['change_pct']<=RED_DROP", "q['change_pct']<=RED_DROP or q.get('broke_low_deep')", 1)
lines[yellow] = lines[yellow].replace(
    "q['change_pct']<=YELLOW_DROP:", "q['change_pct']<=YELLOW_DROP or q['broke_low']:", 1)
lines.insert(const + 1, 'LOW_BREAK_RED = 2.0  # пробой 10-дн. минимума на столько % и больше — красный флаг, меньше — жёлтый')

backup = TARGET.with_name('stocks.py.bak-' + time.strftime('%Y%m%d-%H%M%S'))
shutil.copy2(TARGET, backup)
TARGET.write_text('\n'.join(lines))
try:
    py_compile.compile(str(TARGET), doraise=True)
except py_compile.PyCompileError as e:
    shutil.copy2(backup, TARGET)
    sys.exit('ошибка синтаксиса, откатил из %s:\n%s' % (backup.name, e))
print('бэкап:', backup.name)
print('изменённые строки:')
for i in [const + 1] + [c + 1 for c in changed]:
    print('%4d: %s' % (i + 1, lines[i]))
