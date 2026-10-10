"""Цвет значков по разделу + дата/время в алертах.

  * fmt_line(q, dot=None): если передан dot, он ставится вместо 🔺/🔻.
  * Отчёт: «Сильный рост» и «Остальные» — 🟢, «Жёлтые флаги» — 🟡,
    «Красные флаги» — как было (🔻/🔺).
  * Алерты «КРАСНЫЙ ФЛАГ» и «Резкий рост»: в заголовке дата и время,
    в «Резком росте» значки 🟢.

Запуск:  cd /opt/stocks && venv/bin/python patch_marks.py
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
if 'def fmt_line(q, dot=None):' in src:
    sys.exit('уже применено, изменений нет')
lines = src.split('\n')
changed = set()
GREEN, YELLOW = '🟢', '🟡'
STAMP = "datetime.now(TZ).strftime('%d.%m.%Y %H:%M')"


def find(pred, start=0):
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    return None


def must(i, what):
    if i is None:
        sys.exit('не нашёл «%s» — ничего не менял' % what)
    return i


# 1. fmt_line: параметр dot
d = must(find(lambda l: l.startswith('def fmt_line(q):')), 'def fmt_line(q):')
lines[d] = 'def fmt_line(q, dot=None):'
changed.add(d)
end = find(lambda l: l.startswith('def '), d + 1) or len(lines)
inserts = []
for i in range(d + 1, end):
    m = re.match(r'(\s*)(arrow|warrow)=.*🔻', lines[i])
    if m:
        inserts.append((i + 1, '%sif dot: %s=dot' % (m.group(1), m.group(2))))
if len(inserts) != 2:
    sys.exit('в fmt_line ожидал 2 строки arrow/warrow, нашёл %d — ничего не менял' % len(inserts))


# 2. вызовы fmt_line(...) в разделах -> fmt_line(..., dot='🟢'/'🟡')
def colorize(a, b, dot):
    n = 0
    for i in range(a, b):
        new = re.sub(r"fmt_line\(([^()]+)\)", lambda m: "fmt_line(%s, dot='%s')" % (m.group(1), dot), lines[i])
        if new != lines[i]:
            lines[i] = new
            changed.add(i)
            n += 1
    return n


def next_def(i):
    return find(lambda l: l.startswith('def '), i + 1) or len(lines)


strong = must(find(lambda l: 'Сильный рост:' in l and 'append' in l), 'Сильный рост:')
yel = must(find(lambda l: 'Жёлтые' in l and 'append' in l), 'Жёлтые флаги:')
rest = must(find(lambda l: 'Остальные' in l and 'append' in l), 'Остальные')
report = {
    'Сильный рост': colorize(strong, yel, GREEN),
    'Жёлтые': colorize(yel, rest, YELLOW),
    'Остальные': colorize(rest, next_def(rest), GREEN),
}

# 3. алерты: дата/время в заголовке, 🟢 в «Резком росте»
red_hdr = must(find(lambda l: 'требует внимания</b>' in l and 'lines=[' in l), 'КРАСНЫЙ ФЛАГ — требует внимания')
spike_hdr = must(find(lambda l: 'Резкий рост</b>' in l and 'lines=[' in l), 'Резкий рост</b>')
for i in (red_hdr, spike_hdr):
    lines[i] = lines[i].replace("</b>'", "</b> · '+" + STAMP, 1)
    changed.add(i)
spike_end = min(x for x in (find(lambda l: 'lines=[' in l, spike_hdr + 1), next_def(spike_hdr)) if x is not None)
report['алерт Резкий рост'] = colorize(spike_hdr + 1, spike_end, GREEN)

# вставки в fmt_line — в последнюю очередь, чтобы не сдвигать номера выше
for pos, text in reversed(inserts):
    lines.insert(pos, text)
    changed = {c + 1 if c >= pos else c for c in changed} | {pos}

backup = TARGET.with_name('stocks.py.bak-' + time.strftime('%Y%m%d-%H%M%S'))
shutil.copy2(TARGET, backup)
TARGET.write_text('\n'.join(lines))
try:
    py_compile.compile(str(TARGET), doraise=True)
except py_compile.PyCompileError as e:
    shutil.copy2(backup, TARGET)
    sys.exit('ошибка синтаксиса, откатил из %s:\n%s' % (backup.name, e))
print('бэкап:', backup.name)
print('вызовов fmt_line перекрашено:', ', '.join('%s %d' % kv for kv in report.items()))
print('изменённые строки:')
for i in sorted(changed):
    print('%4d: %s' % (i + 1, lines[i]))
