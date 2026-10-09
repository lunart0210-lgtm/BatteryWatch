"""Источники данных для /opt/stocks/stocks.py.

  * stooq_candles(symbol) — дневная история акций/ETF со Stooq (без ключа).
    Возвращает словарь в формате Finnhub stock/candle: {'s': 'ok', 'c': [...]},
    поэтому заменяет вызов finnhub_get('stock/candle', ...) один к одному.
  * cmc_quotes(symbols)   — котировки крипты с CoinMarketCap (бесплатный Basic).
    Один запрос на все монеты; отдаёт цену и изменения за 24ч / 7д / 30д.

Проверка на VPS:  venv/bin/python sources.py stock ABBV SLV
                  venv/bin/python sources.py crypto BTC ETH
"""
import csv
import datetime as dt
import io
import logging
import os
import pathlib
import time

import requests

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo('America/New_York')
except Exception:  # старый Python без tzdata
    NY = None

HERE = pathlib.Path(__file__).resolve().parent
STOOQ_URL = 'https://stooq.com/q/d/l/'
CMC_URL = 'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest'
HISTORY_DAYS = 45          # календарных дней истории — хватает на 10 торговых + запас
TIMEOUT = 15
UA = {'User-Agent': 'Mozilla/5.0 (stocks-bot)'}

# Если тикер на Stooq называется иначе — допиши сюда: 'BRK.B': 'brk-b.us'
STOOQ_ALIASES = {}


def _env(name):
    """Берёт переменную из окружения, а если её нет — из /opt/stocks/.env."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = HERE / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, sep, val = line.partition('=')
            if sep and key.strip() == name:
                return val.strip().strip('"').strip("'")
    return None


def _ny_today():
    return dt.datetime.now(NY).date() if NY else dt.datetime.utcnow().date()


# ---------------------------------------------------------------- Stooq

def stooq_symbol(symbol):
    s = symbol.strip()
    if s in STOOQ_ALIASES:
        return STOOQ_ALIASES[s]
    s = s.lower().replace('.', '-')
    return s if s.endswith('.us') else s + '.us'


def stooq_daily(symbol, days=HISTORY_DAYS):
    """[(date, close), ...] от старых к новым. Пустой список, если данных нет."""
    today = _ny_today()
    params = {
        's': stooq_symbol(symbol),
        'i': 'd',
        'd1': (today - dt.timedelta(days=days)).strftime('%Y%m%d'),
        'd2': today.strftime('%Y%m%d'),
    }
    r = requests.get(STOOQ_URL, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.text.strip()
    if not text.lower().startswith('date'):
        # "No data" или сообщение о превышении дневного лимита
        raise RuntimeError('stooq: ' + text[:80].replace('\n', ' '))
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            rows.append((dt.date.fromisoformat(row['Date']), float(row['Close'])))
        except (KeyError, ValueError):
            continue
    rows.sort()
    return rows


def stooq_candles(symbol, **_ignored):
    """Замена finnhub_get('stock/candle', ...).

    Как и у Finnhub, последний элемент 'c' — это «сегодня»: в stocks.py он
    отбрасывается через candles['c'][:-1]. Если сегодняшней свечи ещё нет
    (до открытия биржи, выходные), подставляем последнее закрытие как
    заглушку, чтобы [:-1] срезал её, а не вчерашний завершённый день.
    """
    rows = stooq_daily(symbol)
    if not rows:
        return {'s': 'no_data'}
    closes = [c for _, c in rows]
    if rows[-1][0] < _ny_today():
        closes.append(closes[-1])
    return {'s': 'ok', 'c': closes}


# ---------------------------------------------------------- CoinMarketCap

def cmc_symbol(symbol):
    """'BINANCE:BTCUSDT' / 'BTC-USD' / 'btc' -> 'BTC'."""
    s = symbol.strip().upper().split(':')[-1]
    for suffix in ('-USDT', '-USD', 'USDT', 'USDC', 'USD'):
        if s.endswith(suffix) and len(s) > len(suffix):
            return s[:-len(suffix)]
    return s


def cmc_quotes(symbols):
    """{исходный_символ: {'price', 'change_pct', 'weekly_change_pct',
    'monthly_change_pct', 'name'}} — одним запросом на все монеты."""
    key = _env('CMC_API_KEY')
    if not key:
        raise RuntimeError('CMC_API_KEY не задан в /opt/stocks/.env')
    by_cmc = {}
    for s in symbols:
        by_cmc.setdefault(cmc_symbol(s), []).append(s)
    if not by_cmc:
        return {}
    r = requests.get(
        CMC_URL,
        params={'symbol': ','.join(by_cmc), 'convert': 'USD', 'skip_invalid': 'true'},
        headers={'X-CMC_PRO_API_KEY': key, 'Accept': 'application/json'},
        timeout=TIMEOUT,
    )
    body = r.json()
    status = body.get('status') or {}
    if r.status_code != 200 or status.get('error_code'):
        raise RuntimeError('CMC %s: %s' % (r.status_code, status.get('error_message')))

    out = {}
    for cmc_sym, entries in (body.get('data') or {}).items():
        if isinstance(entries, dict):
            entries = [entries]
        if not entries:
            continue
        # Под одним тикером бывает несколько монет — берём самую крупную.
        coin = min(entries, key=lambda e: e.get('cmc_rank') or 10**9)
        usd = (coin.get('quote') or {}).get('USD') or {}
        if usd.get('price') is None:
            continue
        q = {
            'name': coin.get('name'),
            'price': usd['price'],
            'change_pct': usd.get('percent_change_24h') or 0.0,
            'weekly_change_pct': usd.get('percent_change_7d'),
            'monthly_change_pct': usd.get('percent_change_30d'),
        }
        for original in by_cmc.get(cmc_sym.upper(), []):
            out[original] = q
    missing = [s for s in symbols if s not in out]
    if missing:
        logging.warning('CMC: нет котировок для %s', ', '.join(missing))
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3 or sys.argv[1] not in ('stock', 'crypto'):
        sys.exit('usage: sources.py stock ABBV SLV ... | sources.py crypto BTC ETH ...')
    kind, symbols = sys.argv[1], sys.argv[2:]
    if kind == 'stock':
        for s in symbols:
            try:
                hist = stooq_candles(s)['c'][:-1]
                print('%-6s stooq: %d дней, последнее закрытие %.2f, мин. за 10 дней %.2f'
                      % (s, len(hist), hist[-1], min(hist[-10:])))
            except Exception as e:
                print('%-6s stooq ОШИБКА: %s' % (s, e))
            time.sleep(0.5)
    else:
        try:
            for s, q in cmc_quotes(symbols).items():
                print('%-10s CMC: %.4f  24ч %+.2f%%  7д %+.2f%%'
                      % (s, q['price'], q['change_pct'], q['weekly_change_pct'] or 0))
        except Exception as e:
            print('CMC ОШИБКА:', e)
