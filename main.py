# main.py — production-ready for Render (Background Worker or Web Service)
#
# ✅ Features:
# - Stable infinite loop with backoff + jitter (prevents crash loops)
# - Scans on 15m candle close by default (less spam + fewer API calls)
# - Cooldown/dedup remains handled in notifier.py (if you already have it)
# - Structured logging (Render shows logs in dashboard)
# - Optional lightweight /health HTTP endpoint (works if you deploy as Web Service)
#
# Environment variables (set in Render dashboard):
# - RUN_MODE: "worker" (default) or "web"
# - PORT: (Render sets this automatically for web services)
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
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv

from exchange import make_exchange, fetch_ohlcv_df
from config import SYMBOLS, TIMEFRAMES, PARAMS
from strategy import detect
from notifier import cooldown_ok, send_telegram, format_signal

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
# Optional health server (for Render Web Service)
# ---------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # reduce noisy HTTP logs
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    log.info(f"Health server listening on 0.0.0.0:{port}")
    server.serve_forever()


# ---------------------------
# Scheduling helpers
# ---------------------------
def seconds_until_next_15m_close() -> int:
    """
    Returns seconds until the next 15-minute candle boundary (UTC).
    Adds a small delay buffer (2-5s) to ensure candle is closed on exchange side.
    """
    now = datetime.now(timezone.utc)
    minute = now.minute
    # Next boundary at minute 0, 15, 30, 45
    next_minute = ((minute // 15) + 1) * 15
    next_hour = now.hour
    next_day = now.date()

    if next_minute >= 60:
        next_minute = 0
        next_hour += 1
        if next_hour >= 24:
            next_hour = 0
            # move to next day (simple; datetime handles)
            next_dt = datetime(
                now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc
            ) + (datetime.now(timezone.utc).date() - next_day)  # no-op
            # easier: just add 1 hour and then round, but keep simple below

    # Build next boundary datetime robustly by adding minutes until boundary
    # Compute delta minutes to next boundary:
    delta_minutes = (15 - (minute % 15)) % 15
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
    Scans all symbols once. Exceptions are handled per symbol to avoid whole-bot crash.
    """
    for symbol in SYMBOLS:
        try:
            df15 = fetch_ohlcv_df(ex, symbol, TIMEFRAMES["entry"], limit=300)
            df1h = fetch_ohlcv_df(ex, symbol, TIMEFRAMES["bias"], limit=300)
            df4h = fetch_ohlcv_df(ex, symbol, TIMEFRAMES["regime"], limit=300)

            sig = detect(df15, df1h, df4h, symbol, PARAMS)
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

    run_mode = os.getenv("RUN_MODE", "worker").lower()  # "worker" or "web"
    scan_on_close = os.getenv("SCAN_ON_CANDLE_CLOSE", "1") == "1"
    scan_interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))

    # If deployed as Web Service, run a health endpoint so Render sees it as "up"
    if run_mode == "web":
        Thread(target=start_health_server, daemon=True).start()

    log.info("Starting Bitget Futures Analysis Bot")
    log.info(f"RUN_MODE={run_mode} | SCAN_ON_CANDLE_CLOSE={scan_on_close} | SYMBOLS={len(SYMBOLS)}")

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