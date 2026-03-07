import os, json, time, requests
from datetime import datetime, timezone

CACHE_PATH = "storage/sent_cache.json"

def _load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def _save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f)

def cooldown_ok(key, minutes):
    cache = _load_cache()
    now = int(time.time())
    last = cache.get(key, 0)
    if now - last < minutes * 60:
        return False
    cache[key] = now
    _save_cache(cache)
    return True

def send_telegram(text: str):
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        raise ValueError("Missing TG_BOT_TOKEN or TG_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=10,
    )

def format_signal(sig):
    side_label = "🟢 <b>LONG</b>" if sig.side == "LONG" else "🔴 <b>SHORT</b>"
    return (
        f"Pair: <b>{sig.symbol}</b>\n"
        f"Side: {side_label}\n"
        f"Entry: {sig.entry:.4f}\n"
        f"SL: {sig.sl:.4f}\n"
        f"TP1: {sig.tp1:.4f} | TP2: {sig.tp2:.4f}\n"
        f"RR: 1:{sig.rr:.2f} | Score: {sig.score}/100\n"
        f"Reason: {sig.reason}\n"
        f"Invalidate: {sig.invalidate}"
    )
