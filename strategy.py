from dataclasses import dataclass
import pandas as pd

@dataclass
class Signal:
    symbol: str
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    rr: float
    score: int
    reason: str
    invalidate: str


def _ma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def _atr(df: pd.DataFrame, length: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1
    ).max(axis=1)

    return tr.rolling(length).mean()


def _cross_up(a: pd.Series, b: pd.Series) -> bool:
    return float(a.iloc[-2]) <= float(b.iloc[-2]) and float(a.iloc[-1]) > float(b.iloc[-1])


def _cross_down(a: pd.Series, b: pd.Series) -> bool:
    return float(a.iloc[-2]) >= float(b.iloc[-2]) and float(a.iloc[-1]) < float(b.iloc[-1])


def detect(df15: pd.DataFrame, df1h: pd.DataFrame, df4h: pd.DataFrame, symbol: str, p: dict):
    """
    Scalping Mode (MA 7/14/28):
    - Trend/Bias (1H): MA7 > MA14 > MA28 (long) or MA7 < MA14 < MA28 (short)
    - Entry (15m): MA7 crosses MA14 in trend direction and price on correct side of MA28
    """

    ma_fast = int(p.get("ma_fast", 7))
    ma_mid = int(p.get("ma_mid", 14))
    ma_slow = int(p.get("ma_slow", 28))

    min_rows = max(ma_slow, int(p.get("atr_len", 14))) + 2
    if len(df15) < min_rows or len(df1h) < min_rows:
        return None

    # -------------------
    # 1H Trend/Bias
    # -------------------
    c1 = df1h["close"]
    ma7_1h = _ma(c1, ma_fast)
    ma14_1h = _ma(c1, ma_mid)
    ma28_1h = _ma(c1, ma_slow)

    last_close_1h = float(c1.iloc[-1])
    last_ma7_1h = float(ma7_1h.iloc[-1])
    last_ma14_1h = float(ma14_1h.iloc[-1])
    last_ma28_1h = float(ma28_1h.iloc[-1])

    long_trend = last_ma7_1h > last_ma14_1h > last_ma28_1h and last_close_1h > last_ma28_1h
    short_trend = last_ma7_1h < last_ma14_1h < last_ma28_1h and last_close_1h < last_ma28_1h

    if not long_trend and not short_trend:
        return None

    # -------------------
    # 15m Entry
    # -------------------
    c15 = df15["close"]
    ma7_15 = _ma(c15, ma_fast)
    ma14_15 = _ma(c15, ma_mid)
    ma28_15 = _ma(c15, ma_slow)
    atr15 = _atr(df15, p["atr_len"])

    last_close_15 = float(c15.iloc[-1])
    last_ma28_15 = float(ma28_15.iloc[-1])
    last_atr_15 = float(atr15.iloc[-1]) if pd.notna(atr15.iloc[-1]) else None

    if last_atr_15 is None or last_atr_15 <= 0:
        return None

    score = 0
    score += 30  # trend

    if long_trend:
        if not _cross_up(ma7_15, ma14_15):
            return None
        if last_close_15 <= last_ma28_15:
            return None

        score += 20  # cross
        score += 10  # price > MA28

        entry = last_close_15
        sl = entry - float(p["atr_mult"]) * last_atr_15
        risk = entry - sl
        if risk <= 0:
            return None

        tp1 = entry + float(p["min_rr"]) * risk
        tp2 = entry + 2.0 * risk

        rr = (tp1 - entry) / risk
        reason = "Scalp: 1H uptrend (MA7>MA14>MA28) + 15m MA7 cross up MA14 above MA28"
        invalidate = "15m close below MA28"
        side = "LONG"

    else:
        if not _cross_down(ma7_15, ma14_15):
            return None
        if last_close_15 >= last_ma28_15:
            return None

        score += 20
        score += 10

        entry = last_close_15
        sl = entry + float(p["atr_mult"]) * last_atr_15
        risk = sl - entry
        if risk <= 0:
            return None

        tp1 = entry - float(p["min_rr"]) * risk
        tp2 = entry - 2.0 * risk

        rr = (entry - tp1) / risk
        reason = "Scalp: 1H downtrend (MA7<MA14<MA28) + 15m MA7 cross down MA14 below MA28"
        invalidate = "15m close above MA28"
        side = "SHORT"

    if rr < float(p["min_rr"]):
        return None

    if score < int(p.get("min_score", 55)):
        return None

    return Signal(symbol, side, entry, sl, tp1, tp2, rr, score, reason, invalidate)
