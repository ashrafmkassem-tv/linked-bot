import os, json, requests, base64
from datetime import datetime, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ashrafmkassem-tv/linked-bot")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_PATH = os.getenv("GITHUB_JSON_PATH", "gainz-5stocks/gainz_alpha_5.json")

signals_cache = []

def push_to_github(data_list):
    try:
        if not GITHUB_TOKEN: return False
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None
        content = base64.b64encode(json.dumps(data_list, indent=2).encode()).decode()
        payload = {"message": f"update signals {datetime.now(timezone.utc).isoformat()}", "content": content, "branch": GITHUB_BRANCH}
        if sha: payload["sha"] = sha
        pr = requests.put(url, headers=headers, json=payload)
        print(f"GitHub push: {pr.status_code}")
        return pr.status_code in [200,201]
    except Exception as e:
        print(f"GitHub error: {e}")
        return False

def get_from_github():
    try:
        if not GITHUB_TOKEN: return []
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}?ref={GITHUB_BRANCH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode()
            return json.loads(content)
    except: pass
    return []

def parse_signal(raw_text, json_data):
    data = json_data or {}
    # لو الداتا جاية كـ string جواها json
    if isinstance(data, str):
        try:
            data = json.loads(data.replace('\\"', '"').replace('\\', ''))
        except:
            try: data = json.loads(json.loads(data))
            except: data = {}
    
    # لو raw_text فيه \"
    if not data and raw_text:
        cleaned = raw_text.replace('\\"', '"').replace('\\n','').strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        try:
            data = json.loads(cleaned)
        except: pass

    ticker = str(data.get("ticker") or data.get("symbol") or data.get("Ticker") or "UNKNOWN").upper()
    action = str(data.get("action") or data.get("side") or data.get("signal") or "UNKNOWN").upper()
    price = str(data.get("price") or data.get("close") or data.get("Price") or "")
    timeframe = str(data.get("timeframe") or data.get("interval") or data.get("tf") or "")
    
    # لو لسه UNKNOWN حاول تقرا من النص
    if ticker == "UNKNOWN" and raw_text:
        import re
        m = re.search(r'"ticker"\s*:\s*"([^"]+)"', raw_text, re.I)
        if m: ticker = m.group(1).upper()

    return {
        "ticker": ticker,
        "action": action,
        "price": price,
        "timeframe": timeframe,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "GainzAlgo Alpha",
        "raw_message": raw_text[:500]
    }

@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data(as_text=True) or ""
    j = request.get_json(silent=True, force=True)
    print(f"RAW: {raw}")
    print(f"JSON: {j}")
    sig = parse_signal(raw, j)
    
    # لو لسه UNKNOWN وده تيست
    if sig["ticker"] == "UNKNOWN" and "TEST" in raw.upper():
        sig["ticker"] = "TEST"
        sig["action"] = "BUY"

    signals = get_from_github()
    signals.append(sig)
    signals = signals[-500:]
    push_to_github(signals)

    # تليجرام
    if TELEGRAM_TOKEN and TELEGRAM_CHAT:
        try:
            emoji = "🟢" if "BUY" in sig["action"] else "🔴" if "SELL" in sig["action"] else "⚪️"
            txt = f"{emoji} {sig['action']} {sig['ticker']} {sig['price']} {sig['timeframe']}"
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": txt})
        except Exception as e:
            print(f"Telegram error: {e}")

    return jsonify({"status":"ok", "signal": sig})

@app.route("/signals")
def signals():
    data = get_from_github()
    return jsonify(data)

@app.route("/")
def home():
    return "Gainz bot running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
