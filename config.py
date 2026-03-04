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
  "ma28_slope_min_pct": 0.0001,   # 0.01% per candle

  "atr_len": 14,
  "atr_mult": 1.2,
  "min_rr": 1.5,
  "rr_hard_min": 1.3,
  "best_rr": 2.0,

  "body_min_ratio": 0.60,         # body >= 60% of range
  "close_near_ratio": 0.20,       # close within top/bottom 20%
  "wick_max_ratio": 0.40,         # avoid huge wicks

  "max_ma28_dist_pct": 0.012,     # 1.2% from MA28
  "max_ma28_dist_atr": 1.2,       # or 1.2x ATR from MA28

  "cooldown_minutes": 15,
  "min_score": 55
}
