"""Read-only, visible-window data checks. These are not signal readiness checks."""
import json
import math
from collections import Counter, defaultdict
from contextlib import closing

from universal_bot.chart_workspace import readonly, stamp

EXCHANGES = ("binance", "bitget", "okx", "bybit")


def positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def quality_page(database, exchange, symbol, timeframe, first, last, interval):
    if last < first or interval <= 0 or last - first > interval * 10000:
        raise ValueError("데이터 검사 범위가 잘못됐거나 너무 큽니다.")
    identity = stamp(database)
    sources = defaultdict(dict)
    counts = defaultdict(Counter)
    with closing(readonly(database)) as db:
        for ex in dict.fromkeys((*EXCHANGES, exchange)):
            # Include the exchange prefix to use the market/timestamp index.
            for ts, op, hi, lo, cl, volume in db.execute(
                "SELECT timestamp,open,high,low,close,volume FROM ohlcv "
                "WHERE asset_class='crypto' AND exchange=? AND symbol=? AND timeframe=? "
                "AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
                (ex, symbol, timeframe, first, last),
            ):
                counts[ex][ts] += 1
                valid_price = all(positive(v) for v in (op, hi, lo, cl)) and lo <= min(op, cl) <= max(op, cl) <= hi
                valid_volume = isinstance(volume, (int, float)) and math.isfinite(volume) and volume >= 0
                sources[ex][ts] = (valid_price, valid_volume, volume == 0)
    times = sorted(sources[exchange])
    flags = defaultdict(set)
    missing_bars = irregular = invalid_price = invalid_volume = 0
    for i, ts in enumerate(times):
        price_ok, volume_ok, zero = sources[exchange][ts]
        if not price_ok:
            invalid_price += 1
            flags[ts].add("OHLC 오류")
        if not volume_ok:
            invalid_volume += 1
            flags[ts].add("거래량 오류")
        if zero:
            flags[ts].add("거래량 0")
        if counts[exchange][ts] > 1:
            flags[ts].add("중복 봉")
        if i and ts - times[i-1] != interval:
            delta = ts - times[i-1]
            missing_bars += max(0, (delta - 1) // interval)
            irregular += int(delta % interval != 0)
            flags[ts].add("앞 구간 누락/시간 간격 오류")
    exchange_report = {}
    complete = 0
    for ex in EXCHANGES:
        missing = bad_volume = duplicate = zero = 0
        for ts in times:
            row = sources[ex].get(ts)
            if row is None:
                missing += 1
                flags[ts].add(ex + " 누락")
            else:
                bad_volume += int(not row[1])
                zero += int(row[2])
                duplicate += int(counts[ex][ts] > 1)
                if not row[1] or counts[ex][ts] > 1:
                    flags[ts].add(ex + " 거래량/중복 오류")
        exchange_report[ex] = dict(missing=missing, invalid_volume=bad_volume, duplicate=duplicate, zero_volume=zero)
    for ts in times:
        complete += int(all(ts in sources[ex] and sources[ex][ts][1] and counts[ex][ts] == 1 for ex in EXCHANGES))
    if stamp(database) != identity:
        raise ValueError("검사 중 DB가 변경됐습니다. 다시 불러오세요.")
    return json.dumps(dict(bars=len(times), missing_bars=missing_bars, irregular_intervals=irregular,
        invalid_ohlc=invalid_price, invalid_volume=invalid_volume, four_exchange_complete=complete,
        exchanges=exchange_report, rows=[dict(timestamp=ts, reasons=sorted(reasons)) for ts, reasons in sorted(flags.items())]), ensure_ascii=False)
