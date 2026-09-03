import os, json, requests, base64, threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ashrafmkassem-tv/linked-bot")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_PATH = os.getenv("GITHUB_JSON_PATH", "gainz-5stocks/gainz_alpha_5.json")

# Lock عشان لو جالك اكتر من اشعار في نفس الثانية ميضربش بعض
github_lock = threading.Lock()

def push_to_github(data_list):
    try:
        if not GITHUB_TOKEN: 
            print("No GITHUB_TOKEN set")
            return False
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=headers, timeout=15)
        sha = r.json().get("sha") if r.status_code == 200 else None
        content = base64.b64encode(json.dumps(data_list, indent=2).encode()).decode()
        payload = {"message": f"update signals {datetime.now(timezone.utc).isoformat()}", "content": content, "branch": GITHUB_BRANCH}
        if sha: payload["sha"] = sha
        pr = requests.put(url, headers=headers, json=payload, timeout=20)
        print(f"GitHub push: {pr.status_code}")
        return pr.status_code in [200, 201]
    except Exception as e:
        print(f"GitHub error: {e}")
        return False

def get_from_github():
    try:
        if not GITHUB_TOKEN: return []
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}?ref={GITHUB_BRANCH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode()
            return json.loads(content)
    except Exception as e:
        print(f"GitHub get error: {e}")
    return []

def parse_signal(raw_text, json_data):
    data = json_data or {}
    if isinstance(data, str):
        try:
            cleaned_str = data.replace('\\"', '"').replace('\\\\', '\\')
            data = json.loads(cleaned_str)
        except:
            try: data = json.loads(json.loads(data))
            except: data = {}
    if not data and raw_text:
        cleaned = raw_text.replace('\\"', '"').replace('\\n','').strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        try: data = json.loads(cleaned)
        except: pass

    ticker = str(data.get("ticker") or data.get("symbol") or data.get("Ticker") or "UNKNOWN").upper().strip()
    action = str(data.get("action") or data.get("side") or data.get("signal") or "UNKNOWN").upper().strip()
    price = str(data.get("price") or data.get("close") or "")
    timeframe = str(data.get("timeframe") or data.get("interval") or data.get("tf") or "")

    if ticker == "UNKNOWN" and raw_text:
        import re
        m = re.search(r'"ticker"\s*:\s*"([^"]+)"', raw_text, re.I)
        if m: ticker = m.group(1).upper().strip()

    return {
        "ticker": ticker,
        "action": action,
        "price": price,
        "timeframe": timeframe,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "GainzAlgo Alpha",
        "raw_message": (raw_text or str(json_data))[:500]
    }

def process_signal_in_background(raw, json_data):
    try:
        sig = parse_signal(raw, json_data)
        if sig["ticker"] == "UNKNOWN" and "TEST" in (raw or "").upper():
            sig["ticker"] = "TEST"
            sig["action"] = "BUY"
        if sig["ticker"] == "UNKNOWN":
            print(f"Skipped UNKNOWN: {raw[:200]}")
            return
        print(f"Processing: {sig['ticker']} {sig['action']} @ {sig['price']}")
        with github_lock:
            signals = get_from_github()
            signals.append(sig)
            signals = signals[-500:]
            push_to_github(signals)
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            try:
                emoji = "🟢" if "BUY" in sig["action"] else "🔴" if "SELL" in sig["action"] else "⚪"
                txt = f"{emoji} {sig['action']} {sig['ticker']} {sig['price']} {sig['timeframe']}".strip()
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": txt}, timeout=10)
            except Exception as e:
                print(f"Telegram error: {e}")
    except Exception as e:
        print(f"Background error: {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data(as_text=True) or ""
    j = request.get_json(silent=True, force=True)
    print(f"Webhook received len={len(raw)}")
    threading.Thread(target=process_signal_in_background, args=(raw, j), daemon=True).start()
    return jsonify({"status": "ok", "received": True}), 200

@app.route("/signals")
def signals():
    return jsonify(get_from_github())

@app.route("/")
def home():
    return "Gainz bot running - generic ticker mode"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
