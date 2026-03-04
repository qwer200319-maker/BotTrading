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
  "ma_slope_min_pct": 0.0001,     # 0.01% per candle
  "ma_align_tol_pct": 0.001,      # 0.1% tolerance for MA alignment
  "price_tol_pct": 0.001,         # 0.1% tolerance for price vs MA

  "atr_len": 14,
  "min_rr": 2.0,
  "rr_hard_min": 2.0,
  "best_rr": 2.0,

  "pullback_lookback": 2,
  "pullback_body_max_ratio": 0.45,
  "pullback_range_max_atr": 1.0,

  "pinbar_body_max_ratio": 0.35,
  "pinbar_wick_body_mult": 2.5,
  "pinbar_opp_wick_max_mult": 1.0,

  "swing_lookback": 5,
  "sl_atr_buffer": 0.0,

  "cooldown_minutes": 15,
  "min_score": 55
}
