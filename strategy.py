import pandas as pd
from dataclasses import dataclass

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


def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def atr(df, length):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(length).mean()


def detect(df15, df1h, df4h, symbol, p):

    if len(df15) < 200:
        return None

    ema200_4h = ema(df4h["close"], p["ema_slow"])
    regime = "BULL" if df4h["close"].iloc[-1] > ema200_4h.iloc[-1] else "BEAR"

    ema200_1h = ema(df1h["close"], p["ema_slow"])
    bias = "LONG" if df1h["close"].iloc[-1] > ema200_1h.iloc[-1] else "SHORT"

    if regime == "BULL" and bias != "LONG":
        return None
    if regime == "BEAR" and bias != "SHORT":
        return None

    ema50_15 = ema(df15["close"], p["ema_fast"])
    atr15 = atr(df15, p["atr_len"])

    close = df15["close"].iloc[-1]
    ema50 = ema50_15.iloc[-1]
    atrv = atr15.iloc[-1]

    dist = abs(close - ema50) / close
    if dist > p["pullback_pct"]:
        return None

    if regime == "BULL":
        entry = close
        sl = entry - p["atr_mult"] * atrv
        risk = entry - sl
        tp1 = entry + p["min_rr"] * risk
        tp2 = entry + 2.5 * risk
        side = "LONG"
    else:
        entry = close
        sl = entry + p["atr_mult"] * atrv
        risk = sl - entry
        tp1 = entry - p["min_rr"] * risk
        tp2 = entry - 2.5 * risk
        side = "SHORT"

    rr = abs(tp1 - entry) / risk
    if rr < p["min_rr"]:
        return None

    return Signal(
        symbol, side, entry, sl, tp1, tp2, rr,
        60,
        "Aggressive Swing Setup",
        "Structure break"
    )