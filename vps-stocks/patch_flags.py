"""Пробой 10-дневного минимума: красный флаг -> жёлтый.

Красный остаётся только при падении за день или за неделю <= RED_DROP.
Запуск:  cd /opt/stocks && venv/bin/python patch_flags.py
Делает бэкап stocks.py.bak-<время>, при ошибке синтаксиса откатывается.
"""
import pathlib
import py_compile
import shutil
import sys
import time

TARGET = pathlib.Path(__file__).resolve().parent / 'stocks.py'
lines = TARGET.read_text().split('\n')

red = [i for i, l in enumerate(lines) if "return 'red'" in l and "q['broke_low']" in l]
yellow = [i for i, l in enumerate(lines) if "q['change_pct']<=YELLOW_DROP:" in l and "return 'yellow'" in l]
done_yellow = [i for i, l in enumerate(lines) if "YELLOW_DROP or q['broke_low']" in l]

if not red and done_yellow:
    sys.exit('уже применено, изменений нет')
if len(red) != 1 or len(yellow) != 1:
    sys.exit('не нашёл ровно по одной строке red/yellow (%d/%d) — ничего не менял' % (len(red), len(yellow)))

before = (lines[red[0]], lines[yellow[0]])
lines[red[0]] = lines[red[0]].replace(" or q['broke_low']", '', 1)
lines[yellow[0]] = lines[yellow[0]].replace(
    "q['change_pct']<=YELLOW_DROP:", "q['change_pct']<=YELLOW_DROP or q['broke_low']:", 1)
if "broke_low" in lines[red[0]]:
    sys.exit('неожиданный вид строки red — ничего не менял:\n' + before[0])

backup = TARGET.with_name('stocks.py.bak-' + time.strftime('%Y%m%d-%H%M%S'))
shutil.copy2(TARGET, backup)
TARGET.write_text('\n'.join(lines))
try:
    py_compile.compile(str(TARGET), doraise=True)
except py_compile.PyCompileError as e:
    shutil.copy2(backup, TARGET)
    sys.exit('ошибка синтаксиса, откатил из %s:\n%s' % (backup.name, e))
print('бэкап:', backup.name)
print('было:\n  %s\n  %s' % before)
print('стало:\n  %s\n  %s' % (lines[red[0]], lines[yellow[0]]))
