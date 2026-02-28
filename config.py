SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "ASTER/USDT:USDT",
]

TIMEFRAMES = {
    "entry": "15m",
    "bias": "1h",
    "regime": "4h",
}

PARAMS = {
  "ema_fast": 50,
  "ema_slow": 200,
  "atr_len": 14,

  "atr_mult": 1.2,
  "pullback_pct": 0.008,   # 0.8%
  "min_rr": 1.5,

  "cooldown_minutes": 15,
  "min_score": 55
}