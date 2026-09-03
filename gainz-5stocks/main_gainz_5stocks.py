import os
import json
import re
import threading
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- ENV VARS ---
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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # NO MARKDOWN - plain text only to avoid 400 errors
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram response: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"Telegram error: {e}")

def push_to_github():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        import base64
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        sha = None
        get_resp = requests.get(api_url + f"?ref={GITHUB_BRANCH}", headers=headers, timeout=10)
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        data = {
            "message": f"Update {GITHUB_FILE_PATH} - {datetime.now(timezone.utc).isoformat()}",
            "content": b64_content,
            "branch": GITHUB_BRANCH
        }
        if sha:
            data["sha"] = sha
        put_resp = requests.put(api_url, headers=headers, json=data, timeout=15)
        print(f"GitHub push: {put_resp.status_code}")
    except Exception as e:
        print(f"GitHub push error: {e}")

def log_signal(signal_data):
    ensure_json_file()
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list):
                data = []
    except:
        data = []
    data.append(signal_data)
    data = data[-500:]
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if GITHUB_TOKEN:
        threading.Thread(target=push_to_github, daemon=True).start()

def parse_tradingview_payload(raw_body, json_data):
    ticker = "UNKNOWN"
    action = "UNKNOWN"
    price = ""
    timeframe = ""
    exchange = ""
    if json_data:
        ticker = json_data.get("ticker") or json_data.get("symbol") or json_data.get("stock") or ticker
        action = json_data.get("action") or json_data.get("side") or json_data.get("signal") or action
        price = str(json_data.get("price") or json_data.get("close") or "")
        timeframe = json_data.get("timeframe") or json_data.get("interval") or json_data.get("tf") or ""
        exchange = json_data.get("exchange") or ""
        if isinstance(action, str):
            action = action.upper()
    text = raw_body.strip() if raw_body else ""
    if text and (ticker == "UNKNOWN" or action == "UNKNOWN"):
        m = re.search(r'([A-Z]{1,6})\s+(\d+m|\d+h|\d+D)?\s*(BUY|SELL)', text, re.IGNORECASE)
        if m:
            ticker = m.group(1).upper() if ticker == "UNKNOWN" else ticker
            timeframe = m.group(2) or timeframe
            action = m.group(3).upper() if action == "UNKNOWN" else action
        pm = re.search(r'@\s*([\d\.]+)', text)
        if pm:
            price = pm.group(1)
    return {
        "ticker": str(ticker).upper(),
        "action": str(action).upper(),
        "price": str(price),
        "timeframe": str(timeframe),
        "exchange": str(exchange),
        "raw": text[:500] if text else json.dumps(json_data)[:500] if json_data else ""
    }

def process_signal_async(raw_body, json_data):
    parsed = parse_tradingview_payload(raw_body, json_data)
    now_utc = datetime.now(timezone.utc)
    signal_record = {
        "timestamp_utc": now_utc.isoformat(),
        "ticker": parsed["ticker"],
        "action": parsed["action"],
        "price": parsed["price"],
        "timeframe": parsed["timeframe"],
        "exchange": parsed["exchange"],
        "source": "GainzAlgo Alpha",
        "raw_message": parsed["raw"]
    }
    log_signal(signal_record)
    emoji = "🟢" if "BUY" in parsed["action"] else "🔴" if "SELL" in parsed["action"] else "🔵"
    msg = f"{emoji} GainzAlgo Alpha\n\n"
    msg += f"Ticker: {parsed['ticker']}\n"
    msg += f"Action: {parsed['action']}\n"
    if parsed['price']:
        msg += f"Price: {parsed['price']}\n"
    if parsed['timeframe']:
        msg += f"TF: {parsed['timeframe']}\n"
    msg += f"Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    if parsed['raw']:
        msg += f"\n{parsed['raw']}"
    send_telegram(msg)

@app.route('/', methods=['GET'])
def home():
    ensure_json_file()
    return jsonify({"status": "Gainz 5 Stocks Open Bot is running - NO MARKDOWN - instant response", "mode": "open - accepts any ticker", "json_file": JSON_FILE})

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
    return jsonify({"status": "ok", "received": True}), 200

@app.route('/webhook', methods=['GET'])
def webhook_get():
    return jsonify({"ok": True, "msg": "Use POST"}), 200

@app.route('/signals', methods=['GET'])
def get_signals():
    ensure_json_file()
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data[-100:])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    ensure_json_file()
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
