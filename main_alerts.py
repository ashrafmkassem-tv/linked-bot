import os, json, logging, requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")
app = FastAPI(title="L3 98 FINAL FIXED 70/15/5 0830-1600")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for p in ["L3_sectors.json", "watchlists/L3_sectors.json", "./watchlists/L3_sectors.json"]:
    if os.path.exists(p):
        L3_FILE = p; break
else:
    L3_FILE = "L3_sectors.json"

try:
    with open(L3_FILE, "r") as f:
        sectors = json.load(f)
    all_tickers = [t for lst in sectors.values() for t in lst]
    total = len(all_tickers)
    logger.info(f"ALERTS WATCH 98: {total} FULL BOTH NOW 70 SCORE from {L3_FILE}")
except Exception as e:
    sectors = {}; total = 0
    logger.error(f"Failed {L3_FILE}: {e}")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN_ALERTS") or os.getenv("TELEGRAM_TOKEN") or ""
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID_ALERTS") or ""

_last = {}
def can_send(key, mins):
    now = datetime.utcnow()
    if key in _last and now - _last[key] < timedelta(minutes=mins): return False
    _last[key] = now; return True

def is_ny_session():
    try:
        ny = pytz.timezone("America/New_York")
        n = datetime.now(ny)
        if n.weekday() >= 5: return False
        hm = n.hour*60 + n.minute
        return (8*60+30) <= hm <= (16*60)
    except: return True

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=60)
        return r.status_code == 200
    except: return False

@app.on_event("startup")
async def startup():
    send_telegram(f"🚀 <b>ALERTS BOT 98 FINAL FIXED</b>\n98 Stocks | Score 70+ | CD 15m/5m | 08:30-16:00 NY\nBOTH NOW PRESERVED | {total}")

@app.get("/")
async def root():
    return {"status":"online","tickers":total,"file":L3_FILE,"both_now":True,"sectors":{k:len(v) for k,v in sectors.items()},"ny":is_ny_session()}

@app.post("/webhook")
async def webhook_post(request: Request):
    try: data = await request.json()
    except:
        try: body = await request.body(); data = json.loads(body.decode() if body else "{}")
        except: data={}
    ticker_raw = data.get("ticker") or data.get("symbol") or "UNKNOWN"
    clean = ticker_raw.split(":")[-1] if ":" in ticker_raw else ticker_raw
    clean_u = clean.upper().strip()
    try: score = float(data.get("score",0) or 0)
    except: score = 0
    level = data.get("level",""); price = data.get("price",""); rvol = data.get("rvol","")

    # FIXED 70
    if score!=0 and score < 70:
        return JSONResponse({"status":"skipped","reason":"score <70","score":score})
    # FIXED NY TIME
    if not is_ny_session():
        return JSONResponse({"status":"skipped","reason":"outside 08:30-16:00 NY"})
    # FIXED COOLDOWN 15m / 5m
    is_breakout = "BREAKOUT" in level.upper() or score >= 85
    cooldown_mins = 5 if is_breakout else 15
    if not can_send(f"ALERT_{clean_u}", cooldown_mins):
        return JSONResponse({"status":"cooldown","cd":cooldown_mins})

    msg = f"🔥 <b>L3 ALERT: {clean_u}</b>\nScore: <b>{score}</b> {level}\nPrice: {price} | RVOL: {rvol}\nTicker: {ticker_raw} | CD:{cooldown_mins}m"
    ok = send_telegram(msg)
    return JSONResponse({"status":"ok","ticker":clean_u,"telegram_sent":ok,"score":score,"cd":cooldown_mins})

@app.post("/webhook/ai")
async def webhook_ai(r: Request): return await webhook_post(r)
@app.post("/webhook/tradingview")
async def webhook_tv(r: Request): return await webhook_post(r)
