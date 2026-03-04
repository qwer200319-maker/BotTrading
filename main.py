# main.py — production-ready for Render (Background Worker)
#
# ✅ Features:
# - Stable infinite loop with backoff + jitter (prevents crash loops)
# - Scans on 15m candle close by default (less spam + fewer API calls)
# - Cooldown/dedup remains handled in notifier.py (if you already have it)
# - Structured logging (Render shows logs in dashboard)
#
# Environment variables (set in Render dashboard):
# - SCAN_ON_CANDLE_CLOSE: "1" (default) or "0"
# - SCAN_INTERVAL_SECONDS: default 60 (used when SCAN_ON_CANDLE_CLOSE=0)
#
# Your existing env vars:
# BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE
# TG_BOT_TOKEN, TG_CHAT_ID

import os
import time
import random
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

from exchange import make_exchange, fetch_ohlcv_df
from config import SYMBOLS, TIMEFRAMES, PARAMS
from strategy import detect
from notifier import cooldown_ok, send_telegram, format_signal

# ---------------------------
# Env checks
# ---------------------------
REQUIRED_ENVS = [
    "BITGET_API_KEY",
    "BITGET_API_SECRET",
    "BITGET_API_PASSPHRASE",
    "TG_BOT_TOKEN",
    "TG_CHAT_ID",
]


def warn_missing_env():
    missing = [k for k in REQUIRED_ENVS if not os.getenv(k)]
    if missing:
        log.warning(f"Missing env vars: {', '.join(missing)}")


# ---------------------------
# Logging
# ---------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("bot")

# ---------------------------
# Scheduling helpers
# ---------------------------
def seconds_until_next_15m_close() -> int:
    """
    Returns seconds until the next 15-minute candle boundary (UTC).
    Adds a small delay buffer (2-5s) to ensure candle is closed on exchange side.
    """
    now = datetime.now(timezone.utc)
    # Compute delta minutes to next boundary:
    delta_minutes = (15 - (now.minute % 15)) % 15
    if delta_minutes == 0:
        delta_minutes = 15
    target = now.replace(second=0, microsecond=0) + timedelta_minutes(delta_minutes)

    # Add a small buffer to let exchange finalize candle
    buffer_sec = random.randint(2, 5)
    wait = int((target - now).total_seconds()) + buffer_sec
    return max(wait, 5)


def timedelta_minutes(m: int):
    # tiny helper to avoid importing timedelta at top (keeps it explicit)
    from datetime import timedelta

    return timedelta(minutes=m)


# ---------------------------
# Core scan logic (one cycle)
# ---------------------------
def run_scan_cycle(ex):
    """
    Scans all symbols once using 15m + 1h data only.
    Exceptions are handled per symbol to avoid whole-bot crash.
    """
    for symbol in SYMBOLS:
        try:
            df15 = fetch_ohlcv_df(ex, symbol, TIMEFRAMES["entry"], limit=300)
            df1h = fetch_ohlcv_df(ex, symbol, TIMEFRAMES["bias"], limit=300)
            # Strategy uses only 15m + 1h for now; keep df4h as None
            sig = detect(df15, df1h, symbol, PARAMS)
            if not sig:
                continue

            # Dedup / cooldown by symbol + side (simple)
            key = f"{symbol}:{sig.side}"
            if cooldown_ok(key, PARAMS.get("cooldown_minutes", 30)):
                msg = format_signal(sig)
                send_telegram(msg)
                log.info(f"SENT | {symbol} | {sig.side} | RR={sig.rr:.2f} | Score={sig.score}")
            else:
                log.info(f"SKIP cooldown | {symbol} | {sig.side}")

        except Exception as e:
            # Keep running even if one symbol fails
            log.error(f"ERR {symbol} | {type(e).__name__}: {e}")


# ---------------------------
# Entry point
# ---------------------------
def main():
    load_dotenv()

    scan_on_close = os.getenv("SCAN_ON_CANDLE_CLOSE", "1") == "1"
    scan_interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))

    log.info("Starting Bitget Futures Analysis Bot")
    log.info(f"SCAN_ON_CANDLE_CLOSE={scan_on_close} | SYMBOLS={len(SYMBOLS)}")
    warn_missing_env()

    # Create exchange once; if it fails due to network, we will retry with backoff
    base_backoff = 5
    max_backoff = 180

    ex = None

    while True:
        try:
            if ex is None:
                ex = make_exchange()
                log.info("Exchange client initialized")

            run_scan_cycle(ex)

            if scan_on_close:
                # Sleep until next 15m candle close
                wait = seconds_until_next_15m_close()
                log.info(f"Sleeping until next 15m close: {wait}s")
                time.sleep(wait)
            else:
                # Fixed interval scan
                time.sleep(max(10, scan_interval))

            # reset backoff after successful cycle
            base_backoff = 5

        except KeyboardInterrupt:
            log.info("Received KeyboardInterrupt. Exiting.")
            break

        except Exception as e:
            # If anything critical happens, log and retry with exponential backoff
            log.error(f"FATAL | {type(e).__name__}: {e}")
            ex = None  # force re-init exchange on next loop

            # exponential backoff with jitter
            sleep_for = min(max_backoff, base_backoff) + random.randint(0, 3)
            log.info(f"Retrying in {sleep_for}s...")
            time.sleep(sleep_for)
            base_backoff = min(max_backoff, base_backoff * 2)


if __name__ == "__main__":
    main()
