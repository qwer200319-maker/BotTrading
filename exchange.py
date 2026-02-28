# exchange.py
import os
import time
import random
import logging

import ccxt
import pandas as pd

log = logging.getLogger("bot")


def make_exchange():
    """
    Create a CCXT Bitget client configured for USDT-m perpetual futures (swap).
    - Disables fetchCurrencies (avoids spot/public/coins).
    - Loads markets once.
    """
    ex = ccxt.bitget({
        "apiKey": os.getenv("BITGET_API_KEY"),
        "secret": os.getenv("BITGET_API_SECRET"),
        "password": os.getenv("BITGET_API_PASSPHRASE"),
        "timeout": int(os.getenv("CCXT_TIMEOUT_MS", "20000")),
        "enableRateLimit": True,
        "options": {
            "defaultType": "swap",            # futures perp
            "fetchCurrencies": False,         # IMPORTANT: stop calling spot/public/coins
            "adjustForTimeDifference": True,
        },
    })

    # Extra safety: disable fetchCurrencies capability
    ex.has["fetchCurrencies"] = False

    # Load markets once (needed for symbol parsing); avoids auto-load surprises later.
    ex.load_markets()

    return ex


def normalize_symbol(symbol: str) -> str:
    """
    Convert UI format (e.g., BTCUSDT, ASTERUSDT) to CCXT Bitget swap format (BTC/USDT:USDT).
    If the symbol already looks like CCXT (contains '/'), it returns it as-is.
    """
    s = (symbol or "").strip().upper()

    # Already CCXT-like (e.g. BTC/USDT:USDT)
    if "/" in s:
        return s

    # UI style: BTCUSDT -> BTC/USDT:USDT
    if s.endswith("USDT") and len(s) > 4:
        base = s[:-4]
        return f"{base}/USDT:USDT"

    raise ValueError(f"Unsupported symbol format: {symbol!r}")


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
    """
    Fetch OHLCV into a pandas DataFrame (UTC timestamp).
    Uses Bitget USDT futures productType.
    """
    ohlcv = _fetch_ohlcv_with_retry(
        ex,
        symbol,
        timeframe=timeframe,
        limit=limit,
        params={"productType": "USDT-FUTURES"},  # force USDT-m futures
        retries=int(os.getenv("CCXT_RETRIES", "3")),
    )
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df