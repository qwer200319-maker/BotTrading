SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    # "SOL/USDT:USDT",
    "ASTER/USDT:USDT",
]

TIMEFRAMES = {
    "entry": "15m",
    "bias": "1h",
}

PARAMS = {
  "ma_fast": 7,
  "ma_mid": 14,
  "ma_slow": 28,
  "ma_slope_min_pct": 0.0001,     # 15m slope check (only if enabled)
  "ma_align_tol_pct": 0.003,      # 0.3% tolerance for MA alignment
  "price_tol_pct": 0.003,         # 0.3% tolerance for price vs MA
  "bias_relaxed": False,
  "bias_mode": "strict",
  "bias_use_slope": True,
  "bias_slope_min_pct": 0.0001,   # 1H: MA slopes must be rising/falling
  "bias_align_tol_pct": 0.0,      # 1H: MA7 > MA14 > MA28 (no tolerance)
  "bias_price_tol_pct": 0.0,      # 1H: close must stay above/below MA7 + MA28
  "bias_chop_lookback": 6,        # 1H: lookback window for chop filter
  "bias_ma_cross_max": 1,         # 1H: max MA7/MA14 crosses allowed
  "bias_price_cross_max": 2,      # 1H: max close/MA14 crosses allowed
  "bias_cross_eps_pct": 0.001,    # 1H: ignore near-equal diffs within 0.1%

  "atr_len": 14,
  "min_rr": 3.0,
  "rr_hard_min": 3.0,
  "best_rr": 3.0,

  "pullback_lookback": 2,
  "pullback_body_max_ratio": 0.45,
  "pullback_range_max_atr": 1.2,
  "pullback_dist_pct": 0.003,     # 0.3% distance allowed
  "pullback_dist_atr": 0.6,       # or 0.6x ATR distance allowed
  "pullback_require_touch": True,
  "pullback_require_small": True,

  "pinbar_body_max_ratio": 0.35,
  "pinbar_wick_body_mult": 2.5,
  "pinbar_opp_wick_max_mult": 1.0,
  "confirm_body_min_ratio": 0.45,
  "confirm_mode": "strict",
  "require_ma28_slope_15m": True,

  "swing_lookback": 5,
  "sl_atr_buffer": 0.0,

  "cooldown_minutes": 15,
  "min_score": 55
}
