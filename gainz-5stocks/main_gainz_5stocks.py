import os
import re
import json
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing TELEGRAM env vars")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram response: {r.status_code} {r.text}")
    except Exception as e:
        print(f"Telegram send failed: {e}")

# Regex for LIVE alerts: TICKER SIGNAL PRICE CHANGE%
# Examples: GELS G10 0.8879 10.99%, KEEL YU5 3.48 5.14%, DVLT R30 0.65 12%
LIVE_PATTERN = re.compile(r'^([A-Z0-9\.\-\_]+)\s+([A-Z]+\d*)\s+([\d\.]+)\s+([\d\.]+)%?', re.IGNORECASE)

def handle_live(raw):
    raw = raw.strip()
    m = LIVE_PATTERN.match(raw)
    if not m:
        # Fallback: try split
        parts = raw.split()
        if len(parts) < 2:
            return None
        ticker = parts[0]
        signal = parts[1] if len(parts) > 1 else ""
        price = parts[2] if len(parts) > 2 else ""
        pct = parts[3] if len(parts) > 3 else ""
    else:
        ticker, signal, price, pct = m.group(1), m.group(2), m.group(3), m.group(4)

    signal_upper = signal.upper()

    if signal_upper.startswith("YU"):
        emoji = "🟡"
        label = f"Yellow Up {signal_upper}"
    elif signal_upper.startswith("YD"):
        emoji = "🟡"
        label = f"Yellow Down {signal_upper}"
    elif signal_upper.startswith("G"):
        emoji = "🟢"
        label = f"Green {signal_upper}"
    elif signal_upper.startswith("R"):
        emoji = "🔴"
        label = f"Red {signal_upper}"
    else:
        emoji = "⚪"
        label = signal_upper

    msg = f"{emoji} LIVE 1M {label}\nTicker: {ticker}\nPrice: {price}\nChange: {pct}%\n\n`{raw}`"
    return msg

def handle_gainz(data, raw_text):
    ticker = data.get("ticker", "UNKNOWN")
    action = str(data.get("action", "UNKNOWN")).lower()
    price = data.get("price", "")
    tf = data.get("timeframe", "")

    if "{" in action or "}" in action:
        print(f"Skipped placeholder action: {raw_text}")
        return None

    emoji = "🔵" if action == "buy" else "🔴" if action == "sell" else "⚪"

    msg = (
        f"{emoji} GainzAlgo Alpha\n"
        f"Ticker: {ticker}\n"
        f"Action: {action.upper()}\n"
        f"Price: {price}\n"
        f"TF: {tf}\n\n"
        f"`{raw_text}`"
    )
    return msg

@app.route("/", methods=["GET", "POST"])
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return "ok", 200

    raw = request.get_data(as_text=True).strip()
    print(f"RAW IN: {raw}")

    if not raw:
        # Try json body if raw empty
        try:
            json_body = request.get_json(force=True, silent=True)
            if json_body:
                raw = json.dumps(json_body)
        except:
            pass

    if not raw:
        return "empty", 200

    # 1. Skip TradingView placeholder alerts like {{STRATEGY.ORDER.ACTION}}
    if "{{" in raw or "STRATEGY" in raw.upper():
        print(f"Skipped bad placeholder: {raw}")
        return "skipped placeholder", 200

    # 2. Try to parse as Gainz JSON first
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "ticker" in data:
            msg = handle_gainz(data, raw)
            if msg:
                send_telegram(msg)
                return "gainz ok", 200
    except:
        pass

    # 3. Try LIVE format
    if any(x in raw.upper() for x in ["G10", "G5", "G15", "YU", "YD", "R30", "R10"]):
        msg = handle_live(raw)
        if msg:
            send_telegram(msg)
            return "live ok", 200

    # 4. Last fallback - try live regex even without keywords
    if LIVE_PATTERN.match(raw):
        msg = handle_live(raw)
        if msg:
            send_telegram(msg)
            return "live ok fallback", 200

    print(f"Unrecognized format: {raw}")
    # Optional: send as unknown for debugging
    # send_telegram(f"⚪ Unknown Format\n`{raw}`")
    return "unknown format", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
