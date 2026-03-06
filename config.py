SYMBOLS = [
    "BTC/USDT:USDT",
    # "ETH/USDT:USDT",
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
  "ma_slope_min_pct": 0.0,        # allow flat MA for aggressive signals
  "ma_align_tol_pct": 0.003,      # 0.3% tolerance for MA alignment
  "price_tol_pct": 0.003,         # 0.3% tolerance for price vs MA
  "bias_relaxed": True,
  "bias_mode": "ma7_ma28",
  "bias_use_slope": False,

  "atr_len": 14,
  "min_rr": 1.3,
  "rr_hard_min": 1.2,
  "best_rr": 2.0,

  "pullback_lookback": 1,
  "pullback_body_max_ratio": 0.75,
  "pullback_range_max_atr": 2.0,
  "pullback_dist_pct": 0.004,     # 0.4% distance allowed
  "pullback_dist_atr": 0.8,       # or 0.8x ATR distance allowed
  "pullback_require_touch": False,
  "pullback_require_small": False,

  "pinbar_body_max_ratio": 0.50,
  "pinbar_wick_body_mult": 2.0,
  "pinbar_opp_wick_max_mult": 1.5,
  "confirm_body_min_ratio": 0.30,
  "confirm_mode": "loose",
  "require_ma28_slope_15m": False,

  "swing_lookback": 5,
  "sl_atr_buffer": 0.0,

  "cooldown_minutes": 15,
  "min_score": 55
}
