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


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


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


def _is_bullish(df15: pd.DataFrame, ema50: float) -> bool:
    """
    Aggressive bullish trigger:
    - candle closes green (close > open)
    AND (closes above EMA50 OR 'reclaim' EMA50 from below)
    """
    o2 = float(df15["open"].iloc[-1])
    c2 = float(df15["close"].iloc[-1])
    o1 = float(df15["open"].iloc[-2])
    c1 = float(df15["close"].iloc[-2])

    green = c2 > o2

    closes_above = c2 >= ema50
    reclaim = (c1 < ema50) and (c2 > ema50)

    # extra small strength: current close above previous close
    strength = c2 >= c1

    return green and (closes_above or reclaim) and strength


def _is_bearish(df15: pd.DataFrame, ema50: float) -> bool:
    """
    Aggressive bearish trigger:
    - candle closes red (close < open)
    AND (closes below EMA50 OR 'reject' EMA50 from above)
    """
    o2 = float(df15["open"].iloc[-1])
    c2 = float(df15["close"].iloc[-1])
    o1 = float(df15["open"].iloc[-2])
    c1 = float(df15["close"].iloc[-2])

    red = c2 < o2

    closes_below = c2 <= ema50
    reject = (c1 > ema50) and (c2 < ema50)

    strength = c2 <= c1

    return red and (closes_below or reject) and strength


def detect(df15: pd.DataFrame, df1h: pd.DataFrame, df4h: pd.DataFrame, symbol: str, p: dict):
    """
    Aggressive Swing Mode:
    - Regime (4H): close vs EMA200 (looser)
    - Bias (1H): close vs EMA200
    - Entry (15m): pullback near EMA50 (wider) + simple trigger candle
    """

    # Safety: need enough rows
    if len(df15) < 210 or len(df1h) < 210 or len(df4h) < 210:
        return None

    # -------------------
    # 4H Regime (looser)
    # -------------------
    c4 = df4h["close"]
    ema200_4h = _ema(c4, p["ema_slow"])
    last_close_4h = float(c4.iloc[-1])
    last_ema200_4h = float(ema200_4h.iloc[-1])

    if last_close_4h > last_ema200_4h:
        regime = "BULL"
    elif last_close_4h < last_ema200_4h:
        regime = "BEAR"
    else:
        return None

    # -------------------
    # 1H Bias (simple)
    # -------------------
    c1 = df1h["close"]
    ema200_1h = _ema(c1, p["ema_slow"])
    last_close_1h = float(c1.iloc[-1])
    last_ema200_1h = float(ema200_1h.iloc[-1])

    bias = "LONG" if last_close_1h > last_ema200_1h else "SHORT"

    # Enforce direction
    if (regime == "BULL" and bias != "LONG") or (regime == "BEAR" and bias != "SHORT"):
        return None

    # -------------------
    # 15m Entry
    # -------------------
    c15 = df15["close"]
    ema50_15 = _ema(c15, p["ema_fast"])
    atr15 = _atr(df15, p["atr_len"])

    last_close_15 = float(c15.iloc[-1])
    last_ema50_15 = float(ema50_15.iloc[-1])
    last_atr_15 = float(atr15.iloc[-1]) if pd.notna(atr15.iloc[-1]) else None

    if last_atr_15 is None or last_atr_15 <= 0:
        return None

    # Pullback check (aggressive: wider zone + wick touch accepted)
    last_high = float(df15["high"].iloc[-1])
    last_low = float(df15["low"].iloc[-1])

    dist = abs(last_close_15 - last_ema50_15) / max(last_close_15, 1e-9)
    near = dist <= float(p["pullback_pct"])
    wick_touch = (last_low <= last_ema50_15 <= last_high)

    if not (near or wick_touch):
        return None

    # Trigger candle (aggressive)
    score = 0
    score += 25  # regime
    score += 20  # bias
    score += 10  # pullback

    if regime == "BULL":
        if not _is_bullish(df15, last_ema50_15):
            return None
        score += 15

        entry = last_close_15
        sl = entry - float(p["atr_mult"]) * last_atr_15
        risk = entry - sl
        if risk <= 0:
            return None

        tp1 = entry + float(p["min_rr"]) * risk
        tp2 = entry + 2.5 * risk

        rr = (tp1 - entry) / risk
        reason = "Aggressive: 4H bull + 1H long + 15m pullback EMA50 + bullish close/reclaim"
        invalidate = "15m close below EMA50"
        side = "LONG"

    else:
        if not _is_bearish(df15, last_ema50_15):
            return None
        score += 15

        entry = last_close_15
        sl = entry + float(p["atr_mult"]) * last_atr_15
        risk = sl - entry
        if risk <= 0:
            return None

        tp1 = entry - float(p["min_rr"]) * risk
        tp2 = entry - 2.5 * risk

        rr = (entry - tp1) / risk
        reason = "Aggressive: 4H bear + 1H short + 15m pullback EMA50 + bearish close/reject"
        invalidate = "15m close above EMA50"
        side = "SHORT"

    # RR / score gates (aggressive uses lower min_score)
    if rr < float(p["min_rr"]):
        return None

    if score < int(p.get("min_score", 55)):
        return None

    return Signal(symbol, side, entry, sl, tp1, tp2, rr, score, reason, invalidate)