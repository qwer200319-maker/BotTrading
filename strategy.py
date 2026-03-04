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


def _slope_ok(ma: pd.Series, i: int, direction: str, min_pct: float) -> bool:
    prev = float(ma.iloc[i - 1])
    curr = float(ma.iloc[i])
    if prev == 0:
        return False
    pct = (curr - prev) / abs(prev)
    if direction == "up":
        return pct >= min_pct
    return pct <= -min_pct


def _strong_candle(df: pd.DataFrame, i: int, direction: str, min_body_ratio: float, close_near_ratio: float, max_wick_ratio: float) -> bool:
    o = float(df["open"].iloc[i])
    c = float(df["close"].iloc[i])
    h = float(df["high"].iloc[i])
    l = float(df["low"].iloc[i])
    rng = h - l
    if rng <= 0:
        return False

    if direction == "bull":
        if c <= o:
            return False
        # Close near high
        if (h - c) / rng > close_near_ratio:
            return False
    else:
        if c >= o:
            return False
        # Close near low
        if (c - l) / rng > close_near_ratio:
            return False

    body = abs(c - o)
    body_ratio = body / rng
    if body_ratio < min_body_ratio:
        return False

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    if max(upper_wick, lower_wick) / rng > max_wick_ratio:
        return False
    return True


def detect(df15: pd.DataFrame, df1h: pd.DataFrame, symbol: str, p: dict):
    """
    Scalping Mode (MA 7/14/28):
    - Trend/Bias (1H): MA7 > MA14 > MA28 (long) or MA7 < MA14 < MA28 (short)
    - Entry (15m): confirmed close with pullback to MA14/28,
      MA alignment intact, MA28 slope in trend direction,
      strong candle close near high/low, and not overextended from MA28
    """

    ma_fast = int(p.get("ma_fast", 7))
    ma_mid = int(p.get("ma_mid", 14))
    ma_slow = int(p.get("ma_slow", 28))
    ma28_slope_min_pct = float(p.get("ma28_slope_min_pct", 0.0))
    body_min_ratio = float(p.get("body_min_ratio", 0.6))
    close_near_ratio = float(p.get("close_near_ratio", 0.2))
    wick_max_ratio = float(p.get("wick_max_ratio", 0.4))
    max_ma28_dist_pct = float(p.get("max_ma28_dist_pct", 0.012))
    max_ma28_dist_atr = p.get("max_ma28_dist_atr", 1.2)
    rr_hard_min = float(p.get("rr_hard_min", 1.3))
    best_rr = float(p.get("best_rr", 2.0))

    if max_ma28_dist_atr is not None:
        max_ma28_dist_atr = float(max_ma28_dist_atr)
        if max_ma28_dist_atr <= 0:
            max_ma28_dist_atr = None

    min_rows = max(ma_slow, int(p.get("atr_len", 14))) + 3
    if len(df15) < min_rows or len(df1h) < min_rows:
        return None

    # -------------------
    # 1H Trend/Bias
    # -------------------
    c1 = df1h["close"]
    ma7_1h = _ma(c1, ma_fast)
    ma14_1h = _ma(c1, ma_mid)
    ma28_1h = _ma(c1, ma_slow)

    # Use last fully closed 1H candle
    bias_i = -2
    last_close_1h = float(c1.iloc[bias_i])
    last_ma7_1h = float(ma7_1h.iloc[bias_i])
    last_ma14_1h = float(ma14_1h.iloc[bias_i])
    last_ma28_1h = float(ma28_1h.iloc[bias_i])

    long_trend = (
        last_ma7_1h > last_ma14_1h > last_ma28_1h
        and last_close_1h > last_ma28_1h
        and _slope_ok(ma28_1h, bias_i, "up", ma28_slope_min_pct)
    )
    short_trend = (
        last_ma7_1h < last_ma14_1h < last_ma28_1h
        and last_close_1h < last_ma28_1h
        and _slope_ok(ma28_1h, bias_i, "down", ma28_slope_min_pct)
    )

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

    # Use the last fully closed 15m candle (avoid the live candle)
    sig_i = -2
    prev_i = -3
    close_sig = float(c15.iloc[sig_i])
    high_sig = float(df15["high"].iloc[sig_i])
    low_sig = float(df15["low"].iloc[sig_i])
    ma7_sig = float(ma7_15.iloc[sig_i])
    ma14_sig = float(ma14_15.iloc[sig_i])
    ma28_sig = float(ma28_15.iloc[sig_i])
    atr_sig = float(atr15.iloc[sig_i]) if pd.notna(atr15.iloc[sig_i]) else None

    if atr_sig is None or atr_sig <= 0:
        return None

    if not pd.notna(ma7_15.iloc[prev_i]) or not pd.notna(ma14_15.iloc[prev_i]) or not pd.notna(ma28_15.iloc[prev_i]):
        return None

    score = 0
    score += 30  # trend

    if long_trend:
        # MA28 slope must be up (avoid flat/sideways)
        if not _slope_ok(ma28_15, sig_i, "up", ma28_slope_min_pct):
            return None

        # Pullback to MA14 or MA28 (touch)
        pullback_ok = low_sig <= ma14_sig or low_sig <= ma28_sig
        if not pullback_ok:
            return None

        # MA alignment still bullish on 15m
        if not (ma7_sig > ma14_sig > ma28_sig):
            return None

        # Candle close above MA7
        if close_sig <= ma7_sig:
            return None

        # Close must remain above MA28 (structure intact)
        if close_sig <= ma28_sig:
            return None

        # Not overextended from MA28
        dist_pct = abs(close_sig - ma28_sig) / max(abs(ma28_sig), 1e-9)
        if dist_pct > max_ma28_dist_pct:
            return None

        # Strong bullish candle (body >= 60%, close near high)
        if not _strong_candle(df15, sig_i, "bull", body_min_ratio, close_near_ratio, wick_max_ratio):
            return None

        # Not overextended from MA28 (percent OR ATR-based)
        dist_pct = abs(close_sig - ma28_sig) / max(abs(ma28_sig), 1e-9)
        dist_atr = abs(close_sig - ma28_sig) / atr_sig
        dist_pct_ok = dist_pct <= max_ma28_dist_pct
        dist_atr_ok = True if max_ma28_dist_atr is None else dist_atr <= max_ma28_dist_atr
        if not (dist_pct_ok or dist_atr_ok):
            return None

        score += 10  # pullback
        score += 20  # alignment
        score += 10  # close > MA7

        entry = close_sig
        sl = entry - float(p["atr_mult"]) * atr_sig
        risk = entry - sl
        if risk <= 0:
            return None

        tp1 = entry + float(p["min_rr"]) * risk
        tp2 = entry + best_rr * risk

        rr = (tp1 - entry) / risk
        reason = "Scalp: 1H uptrend + 15m pullback to MA14/28 + bullish alignment + strong close above MA7"
        invalidate = "15m close below MA7"
        side = "LONG"

    else:
        # MA28 slope must be down (avoid flat/sideways)
        if not _slope_ok(ma28_15, sig_i, "down", ma28_slope_min_pct):
            return None

        # Pullback to MA14 or MA28 (touch)
        pullback_ok = high_sig >= ma14_sig or high_sig >= ma28_sig
        if not pullback_ok:
            return None

        # MA alignment still bearish on 15m
        if not (ma7_sig < ma14_sig < ma28_sig):
            return None

        # Candle close below MA7
        if close_sig >= ma7_sig:
            return None

        # Close must remain below MA28 (structure intact)
        if close_sig >= ma28_sig:
            return None

        # Not overextended from MA28
        dist_pct = abs(close_sig - ma28_sig) / max(abs(ma28_sig), 1e-9)
        if dist_pct > max_ma28_dist_pct:
            return None

        # Strong bearish candle (body >= 60%, close near low)
        if not _strong_candle(df15, sig_i, "bear", body_min_ratio, close_near_ratio, wick_max_ratio):
            return None

        # Not overextended from MA28 (percent OR ATR-based)
        dist_pct = abs(close_sig - ma28_sig) / max(abs(ma28_sig), 1e-9)
        dist_atr = abs(close_sig - ma28_sig) / atr_sig
        dist_pct_ok = dist_pct <= max_ma28_dist_pct
        dist_atr_ok = True if max_ma28_dist_atr is None else dist_atr <= max_ma28_dist_atr
        if not (dist_pct_ok or dist_atr_ok):
            return None

        score += 10
        score += 20
        score += 10

        entry = close_sig
        sl = entry + float(p["atr_mult"]) * atr_sig
        risk = sl - entry
        if risk <= 0:
            return None

        tp1 = entry - float(p["min_rr"]) * risk
        tp2 = entry - best_rr * risk

        rr = (entry - tp1) / risk
        reason = "Scalp: 1H downtrend + 15m pullback to MA14/28 + bearish alignment + strong close below MA7"
        invalidate = "15m close above MA7"
        side = "SHORT"

    if rr < float(p["min_rr"]):
        return None

    if rr < rr_hard_min:
        return None

    if score < int(p.get("min_score", 55)):
        return None

    return Signal(symbol, side, entry, sl, tp1, tp2, rr, score, reason, invalidate)
