import os
import json
import re
import threading
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7486535184").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
GITHUB_FILE_PATH = os.getenv("GITHUB_JSON_PATH", "gainz_alpha_5.json")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

JSON_FILE = "gainz_alpha_5.json"

def ensure_json_file():
    if not os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def log_signal(signal_data):
    ensure_json_file()
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        data = []
    data.append(signal_data)
    data = data[-500:]
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def parse_tradingview_payload(raw_body, json_data):
    ticker = "UNKNOWN"
    action = "UNKNOWN"
    price = ""
    timeframe = ""
    if json_data:
        ticker = json_data.get("ticker") or ticker
        action = json_data.get("action") or action
        price = str(json_data.get("price") or "")
        timeframe = json_data.get("timeframe") or ""
        action = action.upper() if isinstance(action, str) else action
    text = raw_body.strip() if raw_body else ""
    if text and (ticker == "UNKNOWN" or action == "UNKNOWN"):
        m = re.search(r'([A-Z]{1,6})\s+(\d+m|\d+h|\d+D)?\s*(BUY|SELL)', text, re.IGNORECASE)
        if m:
            ticker = m.group(1).upper()
            timeframe = m.group(2) or timeframe
            action = m.group(3).upper()
        pm = re.search(r'@\s*([\d\.]+)', text)
        if pm:
            price = pm.group(1)
    return {"ticker": str(ticker).upper(), "action": str(action).upper(), "price": str(price), "timeframe": str(timeframe), "raw": text[:500]}

def process_signal_async(raw_body, json_data):
    parsed = parse_tradingview_payload(raw_body, json_data)
    now_utc = datetime.now(timezone.utc)
    signal_record = {
        "timestamp_utc": now_utc.isoformat(),
        "ticker": parsed["ticker"],
        "action": parsed["action"],
        "price": parsed["price"],
        "timeframe": parsed["timeframe"],
        "source": "GainzAlgo Alpha",
        "raw_message": parsed["raw"]
    }
    log_signal(signal_record)
    emoji = "🟢" if "BUY" in parsed["action"] else "🔴" if "SELL" in parsed["action"] else "🔵"
    msg = f"{emoji} *GainzAlgo Alpha*\n\n*Ticker:* {parsed['ticker']}\n*Action:* {parsed['action']}\n"
    if parsed['price']: msg += f"*Price:* {parsed['price']}\n"
    if parsed['timeframe']: msg += f"*TF:* {parsed['timeframe']}\n"
    msg += f"*Time:* {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n`{parsed['raw']}`"
    send_telegram(msg)

@app.route('/', methods=['GET'])
def home():
    ensure_json_file()
    return jsonify({"status": "Gainz 5 Stocks Open Bot is running", "mode": "open"})

@app.route('/webhook', methods=['POST'])
@app.route('/webhook-stocks', methods=['POST'])
@app.route('/webhook-gainz', methods=['POST'])
def webhook():
    raw_body = request.get_data(as_text=True)
    json_data = None
    try:
        json_data = request.get_json(force=True, silent=True)
    except:
        pass
    threading.Thread(target=process_signal_async, args=(raw_body, json_data), daemon=True).start()
    return jsonify({"status": "ok"}), 200

@app.route('/signals', methods=['GET'])
def get_signals():
    ensure_json_file()
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data[-100:])

if __name__ == '__main__':
    ensure_json_file()
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))