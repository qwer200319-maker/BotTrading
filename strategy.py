from dataclasses import dataclass
from datetime import datetime, timezone
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


def _last_closed_index(df: pd.DataFrame) -> int:
    """
    Returns index of the most recent fully closed candle.
    If exchange includes the live candle, this returns -2; otherwise -1.
    """
    if len(df) < 3:
        return -2
    ts_last = df["ts"].iloc[-1]
    ts_prev = df["ts"].iloc[-2]
    period_sec = (ts_last - ts_prev).total_seconds()
    if period_sec <= 0:
        return -2
    now = datetime.now(timezone.utc)
    if ts_last + pd.Timedelta(seconds=period_sec) <= now:
        return -1
    return -2


def _bullish_engulfing(df: pd.DataFrame, i: int) -> bool:
    o = float(df["open"].iloc[i])
    c = float(df["close"].iloc[i])
    po = float(df["open"].iloc[i - 1])
    pc = float(df["close"].iloc[i - 1])
    return (c > o) and (pc < po) and (c >= po) and (o <= pc)


def _bearish_engulfing(df: pd.DataFrame, i: int) -> bool:
    o = float(df["open"].iloc[i])
    c = float(df["close"].iloc[i])
    po = float(df["open"].iloc[i - 1])
    pc = float(df["close"].iloc[i - 1])
    return (c < o) and (pc > po) and (c <= po) and (o >= pc)


def _bullish_pinbar(df: pd.DataFrame, i: int, body_max_ratio: float, wick_body_mult: float, opp_wick_max_mult: float) -> bool:
    o = float(df["open"].iloc[i])
    c = float(df["close"].iloc[i])
    h = float(df["high"].iloc[i])
    l = float(df["low"].iloc[i])
    rng = h - l
    if rng <= 0 or c <= o:
        return False
    body = abs(c - o)
    if body <= 0:
        return False
    if body / rng > body_max_ratio:
        return False
    upper = h - max(o, c)
    lower = min(o, c) - l
    if lower < wick_body_mult * body:
        return False
    if upper > opp_wick_max_mult * body:
        return False
    return True


def _bearish_pinbar(df: pd.DataFrame, i: int, body_max_ratio: float, wick_body_mult: float, opp_wick_max_mult: float) -> bool:
    o = float(df["open"].iloc[i])
    c = float(df["close"].iloc[i])
    h = float(df["high"].iloc[i])
    l = float(df["low"].iloc[i])
    rng = h - l
    if rng <= 0 or c >= o:
        return False
    body = abs(c - o)
    if body <= 0:
        return False
    if body / rng > body_max_ratio:
        return False
    upper = h - max(o, c)
    lower = min(o, c) - l
    if upper < wick_body_mult * body:
        return False
    if lower > opp_wick_max_mult * body:
        return False
    return True


def _pullback_small(
    df: pd.DataFrame,
    atr: pd.Series,
    sig_i: int,
    lookback: int,
    max_body_ratio: float,
    max_range_atr,
) -> bool:
    for k in range(1, lookback + 1):
        i = sig_i - k
        if i < -len(df):
            return False
        o = float(df["open"].iloc[i])
        c = float(df["close"].iloc[i])
        h = float(df["high"].iloc[i])
        l = float(df["low"].iloc[i])
        rng = h - l
        if rng <= 0:
            return False
        body = abs(c - o)
        if body / rng > max_body_ratio:
            return False
        if max_range_atr is not None:
            atr_i = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else None
            if atr_i is None or atr_i <= 0:
                return False
            if rng > max_range_atr * atr_i:
                return False
    return True


def _swing_low_high(df: pd.DataFrame, sig_i: int, lookback: int) -> tuple[float, float]:
    n = len(df)
    sig_pos = sig_i if sig_i >= 0 else n + sig_i
    start = max(0, sig_pos - lookback + 1)
    window = df.iloc[start : sig_pos + 1]
    swing_low = float(window["low"].min())
    swing_high = float(window["high"].max())
    return swing_low, swing_high


def detect(df15: pd.DataFrame, df1h: pd.DataFrame, symbol: str, p: dict):
    """
    Scalping Mode (MA 7/14/28):
    - 1H: direction filter (alignment + slope + price vs MA7/MA28)
    - 15m: pullback + confirmation candle (engulfing/pin bar) + alignment intact
    """

    detect.last_reason = ""

    def _fail(reason: str):
        detect.last_reason = reason
        return None

    ma_fast = int(p.get("ma_fast", 7))
    ma_mid = int(p.get("ma_mid", 14))
    ma_slow = int(p.get("ma_slow", 28))
    ma_slope_min_pct = float(p.get("ma_slope_min_pct", p.get("ma28_slope_min_pct", 0.0001)))
    pullback_lookback = int(p.get("pullback_lookback", 2))
    pullback_body_max_ratio = float(p.get("pullback_body_max_ratio", 0.45))
    pullback_range_max_atr = p.get("pullback_range_max_atr", 1.0)
    if pullback_range_max_atr is not None:
        pullback_range_max_atr = float(pullback_range_max_atr)
        if pullback_range_max_atr <= 0:
            pullback_range_max_atr = None
    pinbar_body_max_ratio = float(p.get("pinbar_body_max_ratio", 0.35))
    pinbar_wick_body_mult = float(p.get("pinbar_wick_body_mult", 2.5))
    pinbar_opp_wick_max_mult = float(p.get("pinbar_opp_wick_max_mult", 1.0))
    swing_lookback = int(p.get("swing_lookback", 5))
    sl_atr_buffer = float(p.get("sl_atr_buffer", 0.0))
    rr_hard_min = float(p.get("rr_hard_min", p.get("min_rr", 2.0)))
    best_rr = float(p.get("best_rr", p.get("min_rr", 2.0)))

    min_rows = max(ma_slow, int(p.get("atr_len", 14)), swing_lookback) + 3
    if len(df15) < min_rows or len(df1h) < min_rows:
        return _fail("not_enough_rows")

    # -------------------
    # 1H Trend/Bias
    # -------------------
    c1 = df1h["close"]
    ma7_1h = _ma(c1, ma_fast)
    ma14_1h = _ma(c1, ma_mid)
    ma28_1h = _ma(c1, ma_slow)

    bias_i = _last_closed_index(df1h)
    last_close_1h = float(c1.iloc[bias_i])
    last_ma7_1h = float(ma7_1h.iloc[bias_i])
    last_ma14_1h = float(ma14_1h.iloc[bias_i])
    last_ma28_1h = float(ma28_1h.iloc[bias_i])

    long_trend = (
        last_ma7_1h > last_ma14_1h > last_ma28_1h
        and last_close_1h > last_ma7_1h
        and last_close_1h >= last_ma28_1h
        and _slope_ok(ma7_1h, bias_i, "up", ma_slope_min_pct)
        and _slope_ok(ma14_1h, bias_i, "up", ma_slope_min_pct)
        and _slope_ok(ma28_1h, bias_i, "up", ma_slope_min_pct)
    )
    short_trend = (
        last_ma7_1h < last_ma14_1h < last_ma28_1h
        and last_close_1h < last_ma7_1h
        and last_close_1h <= last_ma28_1h
        and _slope_ok(ma7_1h, bias_i, "down", ma_slope_min_pct)
        and _slope_ok(ma14_1h, bias_i, "down", ma_slope_min_pct)
        and _slope_ok(ma28_1h, bias_i, "down", ma_slope_min_pct)
    )

    if not long_trend and not short_trend:
        return _fail("no_1h_trend")

    # -------------------
    # 15m Entry
    # -------------------
    c15 = df15["close"]
    ma7_15 = _ma(c15, ma_fast)
    ma14_15 = _ma(c15, ma_mid)
    ma28_15 = _ma(c15, ma_slow)
    atr15 = _atr(df15, p["atr_len"])

    sig_i = _last_closed_index(df15)
    prev_i = sig_i - 1
    close_sig = float(c15.iloc[sig_i])
    high_sig = float(df15["high"].iloc[sig_i])
    low_sig = float(df15["low"].iloc[sig_i])
    ma7_sig = float(ma7_15.iloc[sig_i])
    ma14_sig = float(ma14_15.iloc[sig_i])
    ma28_sig = float(ma28_15.iloc[sig_i])
    atr_sig = float(atr15.iloc[sig_i]) if pd.notna(atr15.iloc[sig_i]) else None

    if atr_sig is None or atr_sig <= 0:
        return _fail("atr_invalid")
    if not pd.notna(ma7_15.iloc[prev_i]) or not pd.notna(ma14_15.iloc[prev_i]) or not pd.notna(ma28_15.iloc[prev_i]):
        return _fail("ma_nan")

    score = 0
    score += 30  # trend

    if long_trend:
        if not _slope_ok(ma28_15, sig_i, "up", ma_slope_min_pct):
            return _fail("long_ma28_slope")

        if not (ma7_sig > ma14_sig > ma28_sig):
            return _fail("long_alignment")

        pullback_ok = low_sig <= ma14_sig or low_sig <= ma28_sig
        if not pullback_ok:
            return _fail("long_pullback_touch")

        if not _pullback_small(df15, atr15, sig_i, pullback_lookback, pullback_body_max_ratio, pullback_range_max_atr):
            return _fail("long_pullback_momentum")

        bull_confirm = _bullish_engulfing(df15, sig_i) or _bullish_pinbar(
            df15, sig_i, pinbar_body_max_ratio, pinbar_wick_body_mult, pinbar_opp_wick_max_mult
        )
        if not bull_confirm:
            return _fail("long_confirm_candle")

        if close_sig <= ma7_sig:
            return _fail("long_close_below_ma7")

        score += 10  # pullback
        score += 20  # alignment
        score += 10  # confirm

        entry = close_sig
        swing_low, swing_high = _swing_low_high(df15, sig_i, swing_lookback)
        sl = min(swing_low, ma28_sig) - sl_atr_buffer * atr_sig
        risk = entry - sl
        if risk <= 0:
            return _fail("long_risk_invalid")

        tp1 = swing_high
        rr = (tp1 - entry) / risk
        reason = "Scalp: 1H long bias + 15m pullback + bullish confirm candle"
        invalidate = "15m close below MA7"
        side = "LONG"

    else:
        if not _slope_ok(ma28_15, sig_i, "down", ma_slope_min_pct):
            return _fail("short_ma28_slope")

        if not (ma7_sig < ma14_sig < ma28_sig):
            return _fail("short_alignment")

        pullback_ok = high_sig >= ma14_sig or high_sig >= ma28_sig
        if not pullback_ok:
            return _fail("short_pullback_touch")

        if not _pullback_small(df15, atr15, sig_i, pullback_lookback, pullback_body_max_ratio, pullback_range_max_atr):
            return _fail("short_pullback_momentum")

        bear_confirm = _bearish_engulfing(df15, sig_i) or _bearish_pinbar(
            df15, sig_i, pinbar_body_max_ratio, pinbar_wick_body_mult, pinbar_opp_wick_max_mult
        )
        if not bear_confirm:
            return _fail("short_confirm_candle")

        if close_sig >= ma7_sig:
            return _fail("short_close_above_ma7")

        score += 10
        score += 20
        score += 10

        entry = close_sig
        swing_low, swing_high = _swing_low_high(df15, sig_i, swing_lookback)
        sl = max(swing_high, ma28_sig) + sl_atr_buffer * atr_sig
        risk = sl - entry
        if risk <= 0:
            return _fail("short_risk_invalid")

        tp1 = swing_low
        rr = (entry - tp1) / risk
        reason = "Scalp: 1H short bias + 15m pullback + bearish confirm candle"
        invalidate = "15m close above MA7"
        side = "SHORT"

    if rr < float(p["min_rr"]):
        return _fail("rr_below_min")
    if rr < rr_hard_min:
        return _fail("rr_below_hard_min")
    if score < int(p.get("min_score", 55)):
        return _fail("score_below_min")

    tp2 = entry + best_rr * risk if side == "LONG" else entry - best_rr * risk
    return Signal(symbol, side, entry, sl, tp1, tp2, rr, score, reason, invalidate)
