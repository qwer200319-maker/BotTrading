import os
import time
import random
import threading
import logging

from dotenv import load_dotenv
from flask import Flask, jsonify

from exchange import make_exchange, normalize_symbol, fetch_ohlcv_df
from strategy import detect
from notifier import cooldown_ok, send_telegram, format_signal
from config import SYMBOLS, TIMEFRAMES, PARAMS

# ---------------------------
# Logging
# ---------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bot")

# ---------------------------
# Flask app (Render port binding)
# ---------------------------
app = Flask(__name__)

@app.get("/")
def home():
    return jsonify({"ok": True, "service": "bitget-swing-bot", "status": "running"})

@app.get("/health")
def health():
    return jsonify({"ok": True})

# ---------------------------
# Data cache (reduce API calls)
# ---------------------------
CACHE = {}  # key: (symbol_ccxt, tf) -> {"ts": epoch, "df": df}
CACHE_TTL = {
    "15m": 60,
    "1h": 55 * 60,
    "4h": int(3.8 * 3600)
}

def get_df_cached(ex, symbol_ccxt: str, tf: str, limit: int = 300):
    now = time.time()
    key = (symbol_ccxt, tf)
    ttl = CACHE_TTL.get(tf, 60)

    if key in CACHE and (now - CACHE[key]["ts"]) < ttl:
        return CACHE[key]["df"]

    df = fetch_ohlcv_df(ex, symbol_ccxt, tf, limit=limit)
    CACHE[key] = {"ts": now, "df": df}
    return df

# ---------------------------
# Scheduling
# ---------------------------
def sleep_until_next_15m_close():
    now = time.time()
    seconds = 900 - (now % 900)
    buffer_sec = random.randint(2, 5)
    wait = int(seconds) + buffer_sec
    log.info(f"Sleeping until next 15m close: {wait}s")
    time.sleep(max(5, wait))

# ---------------------------
# One scan cycle
# ---------------------------
def run_scan_cycle(ex):
    for raw_symbol in SYMBOLS:
        time.sleep(0.4 + random.random() * 0.7)  # stagger calls

        try:
            symbol_ccxt = normalize_symbol(raw_symbol)

            df15 = get_df_cached(ex, symbol_ccxt, TIMEFRAMES["entry"], limit=300)
            df1h = get_df_cached(ex, symbol_ccxt, TIMEFRAMES["bias"], limit=300)
            df4h = get_df_cached(ex, symbol_ccxt, TIMEFRAMES["regime"], limit=300)

            sig = detect(df15, df1h, df4h, symbol_ccxt, PARAMS)
            if not sig:
                continue

            key = f"{raw_symbol}:{sig.side}"
            if cooldown_ok(key, PARAMS.get("cooldown_minutes", 15)):
                msg = format_signal(sig, display_symbol=raw_symbol)
                send_telegram(msg)
                log.info(f"SENT | {raw_symbol} | {sig.side} | RR={sig.rr:.2f} | score={sig.score}")
            else:
                log.info(f"SKIP cooldown | {raw_symbol} | {sig.side}")

        except Exception as e:
            log.warning(f"ERR {raw_symbol} | {type(e).__name__}: {e}")

# ---------------------------
# Bot thread
# ---------------------------
def bot_worker():
    load_dotenv()

    log.info("Starting Bitget Futures Swing Bot (worker thread)")
    log.info(f"SCAN_ON_CANDLE_CLOSE=True | SYMBOLS={len(SYMBOLS)}")

    ex = make_exchange()
    log.info("Exchange client initialized")

    # One-time test mode
    if os.getenv("TEST_TELEGRAM", "0") == "1":
        try:
            send_telegram("🚀 TEST: main.py Telegram working successfully!")
            log.info("Test Telegram message sent.")
        except Exception as e:
            log.error(f"Telegram test failed: {e}")
        return

    # Optional startup ping
    if os.getenv("TEST_TELEGRAM_ON_START", "0") == "1":
        try:
            send_telegram("✅ Bot started on Render and can send Telegram messages.")
            log.info("Startup Telegram test sent (TEST_TELEGRAM_ON_START=1)")
        except Exception as e:
            log.warning(f"Startup Telegram test failed: {e}")

    while True:
        try:
            run_scan_cycle(ex)
            sleep_until_next_15m_close()
        except Exception as e:
            log.error(f"FATAL | {type(e).__name__}: {e}")
            time.sleep(10)

# ---------------------------
# Entry
# ---------------------------
if __name__ == "__main__":
    # Start bot in background so Flask can bind PORT
    t = threading.Thread(target=bot_worker, daemon=True)
    t.start()

    port = int(os.getenv("PORT", "10000"))
    log.info(f"Starting web server on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)