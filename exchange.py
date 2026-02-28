import os
import ccxt
import pandas as pd

def make_exchange():
    ex = ccxt.bitget({
        "apiKey": os.getenv("BITGET_API_KEY"),
        "secret": os.getenv("BITGET_API_SECRET"),
        "password": os.getenv("BITGET_API_PASSPHRASE"),
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

def fetch_ohlcv_df(ex, symbol, timeframe, limit=300):
    ohlcv = ex.fetch_ohlcv(
        symbol,
        timeframe=timeframe,
        limit=limit,
        params={"productType": "USDT-FUTURES"}  # ✅ force USDT-m futures
    )
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df