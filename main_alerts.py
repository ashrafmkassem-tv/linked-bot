import os, json, logging, requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")
app = FastAPI(title="L3 98 Alerts Bot - Railway FIXED 50 SCORE 0830-1600")
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
    has_both = any("TSXV:NOW" in t for t in all_tickers) and any("NYSE:NOW" in t for t in all_tickers)
    logger.info(f"ALERTS WATCH 98: {total} FULL BOTH NOW={has_both} 50 SCORE 0830-1600 NY from {L3_FILE}")
except Exception as e:
    sectors = {}; total = 0
    logger.error(f"Failed {L3_FILE}: {e}")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN_ALERTS") or os.getenv("TELEGRAM_TOKEN") or ""
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID_ALERTS") or ""

_last = {}
def can_send(k, mins=2):
    now = datetime.utcnow()
    if k in _last and now - _last[k] < timedelta(minutes=mins): return False
    _last[k] = now; return True

def is_ny_session():
    try:
        ny = pytz.timezone("America/New_York")
        n = datetime.now(ny)
        if n.weekday() >= 5: return False
        hm = n.hour*60 + n.minute
        return (8*60+30) <= hm <= (16*60)
    except:
        return True

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning(f"TG env missing TOKEN={bool(TELEGRAM_BOT_TOKEN)} CHAT={bool(TELEGRAM_CHAT_ID)}")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=60)
        logger.info(f"TG {r.status_code}: {text[:100]}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"TG {e}"); return False

@app.on_event("startup")
async def startup():
    logger.info(f"ALERTS WATCH 98: {total} FULL BOTH NOW - 50 SCORE - 0830-1600 NY")
    send_telegram(f"🚀 <b>ALERTS BOT 98 STARTED</b>\n98 Stocks | Score 50+ | 08:30-16:00 NY | BOTH NOW PRESERVED\nTotal: {total}")

@app.get("/")
async def root():
    return {"status":"online","tickers":total,"file":L3_FILE,"both_now":True,"sectors":{k:len(v) for k,v in sectors.items()},"ny_session_now":is_ny_session(),"telegram":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}

@app.get("/health")
async def health():
    return {"ok":True,"tickers":total,"ny":is_ny_session()}

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
    # 50 SCORE filter
    if score!=0 and score < 50:
        return JSONResponse({"status":"skipped","reason":"score <50","score":score,"ticker":clean_u})
    # 08:30-16:00 NY filter
    if not is_ny_session():
        return JSONResponse({"status":"skipped","reason":"outside 08:30-16:00 NY","ticker":clean_u})
    if not can_send(f"ALERT_{clean_u}",2):
        return JSONResponse({"status":"cooldown","ticker":clean_u})
    level = data.get("level",""); price = data.get("price",""); rvol = data.get("rvol",""); trig = data.get("trig",""); inv = data.get("inv",""); tny = data.get("time","")
    pct = data.get("pct","") or data.get("percent","")
    pct_s = f" ({pct}%)" if pct else ""
    msg = f"🔥 <b>L3 ALERT: {clean_u}</b>\nScore: <b>{score}</b> {level}\nPrice: {price}{pct_s} | RVOL: {rvol}\n"
    if trig: msg+=f"Trig: {trig} | Inv: {inv}\n"
    msg+=f"NY: {tny}\nTicker: {ticker_raw} | 98 FULL BOTH NOW"
    ok = send_telegram(msg)
    return JSONResponse({"status":"ok","ticker":clean_u,"telegram_sent":ok,"score":score,"received":data})

@app.post("/webhook/ai")
async def webhook_ai(r: Request): return await webhook_post(r)
@app.post("/webhook/tradingview")
async def webhook_tv(r: Request): return await webhook_post(r)
