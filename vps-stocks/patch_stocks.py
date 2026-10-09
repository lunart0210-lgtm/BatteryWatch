"""Переводит /opt/stocks/stocks.py с Finnhub stock/candle на Stooq.

Запуск:  cd /opt/stocks && venv/bin/python patch_stocks.py
Делает бэкап stocks.py.bak-<время>, при ошибке синтаксиса откатывается.
Повторный запуск безопасен.
"""
import pathlib
import py_compile
import shutil
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / 'stocks.py'
IMPORT_LINE = 'from sources import stooq_candles, cmc_quotes'

src = TARGET.read_text()
orig = src
done = []

# 1. импорт после последнего import верхнего уровня
if IMPORT_LINE not in src:
    lines = src.split('\n')
    last = None
    for i, line in enumerate(lines):
        if line.startswith('def ') or line.startswith('class '):
            break
        if line.startswith('import ') or line.startswith('from '):
            last = i
    if last is None:
        sys.exit('не нашёл блок import в stocks.py — ничего не менял')
    lines.insert(last + 1, IMPORT_LINE)
    src = '\n'.join(lines)
    done.append('добавлен импорт sources')

# 2. finnhub_get('stock/candle', ...) -> stooq_candles(symbol)
marker = "finnhub_get('stock/candle'"
start = src.find(marker)
if start == -1:
    marker = 'finnhub_get("stock/candle"'
    start = src.find(marker)
if start != -1:
    depth, j = 0, start + len('finnhub_get')
    while j < len(src):
        ch = src[j]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                break
        j += 1
    if depth != 0:
        sys.exit('не смог найти конец вызова stock/candle — ничего не менял')
    old_call = src[start:j + 1]
    src = src[:start] + 'stooq_candles(symbol)' + src[j + 1:]
    done.append('candle -> Stooq (было: %s)' % ' '.join(old_call.split()))
elif 'stooq_candles(symbol)' not in src:
    sys.exit('не нашёл вызов stock/candle — ничего не менял')

# 3. запасной 10-дневный минимум только при >=5 днях истории
fn = src.find('def local_10day_low')
if fn != -1:
    old, new = 'len(hist)<2: return None', 'len(hist)<6: return None'
    k = src.find(old, fn)
    nxt = src.find('\ndef ', fn + 1)
    if k != -1 and (nxt == -1 or k < nxt):
        src = src[:k] + new + src[k + len(old):]
        done.append('local_10day_low: минимум 5 дней истории')

if src == orig:
    print('stocks.py уже пропатчен, изменений нет')
else:
    backup = TARGET.with_name('stocks.py.bak-' + time.strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(TARGET, backup)
    TARGET.write_text(src)
    try:
        py_compile.compile(str(TARGET), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(backup, TARGET)
        sys.exit('ошибка синтаксиса, откатил из %s:\n%s' % (backup.name, e))
    print('бэкап:', backup.name)
    for d in done:
        print(' +', d)

print('\nГде сейчас берётся крипта (пришли этот вывод для перехода на CMC):')
for n, line in enumerate(src.split('\n'), 1):
    low = line.lower()
    if 'crypto' in low or 'binance' in low or 'coingecko' in low:
        print('%4d: %s' % (n, line.rstrip()))
