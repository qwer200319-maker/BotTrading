import os
import time
import random
import logging

import ccxt
import pandas as pd

log = logging.getLogger("bot")

def make_exchange():
    ex = ccxt.bitget({
        "apiKey": os.getenv("BITGET_API_KEY"),
        "secret": os.getenv("BITGET_API_SECRET"),
        "password": os.getenv("BITGET_API_PASSPHRASE"),
        "timeout": int(os.getenv("CCXT_TIMEOUT_MS", "20000")),
        "enableRateLimit": True,
        "options": {
            "defaultType": "swap",        # ✅ futures perp
            "fetchCurrencies": False,     # ✅ IMPORTANT: stop calling spot/public/coins
            "adjustForTimeDifference": True,
        },
    })

    # ✅ Extra safety: disable fetchCurrencies capability
    ex.has["fetchCurrencies"] = False

    # ✅ Load markets ONCE (needed for symbol parsing), without currencies
    ex.load_markets()

    return ex

def _fetch_ohlcv_with_retry(ex, symbol, timeframe, limit, params, retries=3):
    """
    Retry transient network issues when calling Bitget OHLCV.
    """
    last_err = None
    for attempt in range(retries):
        try:
            return ex.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=limit,
                params=params,
            )
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
            last_err = e
            # Exponential backoff with jitter, capped
            wait = min(30, (2 ** attempt) + random.random())
            log.warning(
                f"Network issue fetching OHLCV | {symbol} {timeframe} | "
                f"{type(e).__name__}: {e} | retry in {wait:.1f}s"
            )
            time.sleep(wait)
    # Exhausted retries
    raise last_err

def fetch_ohlcv_df(ex, symbol, timeframe, limit=300):
    ohlcv = _fetch_ohlcv_with_retry(
        ex,
        symbol,
        timeframe=timeframe,
        limit=limit,
        params={"productType": "USDT-FUTURES"},  # ✅ force USDT-m futures
        retries=int(os.getenv("CCXT_RETRIES", "3")),
    )
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df
