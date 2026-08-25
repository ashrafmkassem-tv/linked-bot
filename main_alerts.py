import os, json, logging, requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")
app = FastAPI(title="L3 98 Alerts Bot")

# يدور على الملف في الروت او في watchlists/
for p in ["L3_sectors.json", "watchlists/L3_sectors.json", "./watchlists/L3_sectors.json"]:
    if os.path.exists(p):
        L3_FILE = p
        break
else:
    L3_FILE = "L3_sectors.json"

try:
    with open(L3_FILE, "r") as f:
        sectors = json.load(f)
    all_tickers = [t for lst in sectors.values() for t in lst]
    total = len(all_tickers)
    logger.info(f"ALERTS WATCH 98: {total} tickers FULL - BOTH NOW PRESERVED - 50 SCORE - 0830-1600 NY - Loaded from {L3_FILE}")
except Exception as e:
    sectors = {}
    total = 0
    logger.error(f"Failed {L3_FILE}: {e}")

BOT = os.getenv("TELEGRAM_BOT_TOKEN","")
CHAT = os.getenv("TELEGRAM_CHAT_ID","")

def send_tg(text):
    if not BOT or not CHAT: return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", json={"chat_id":CHAT,"text":text,"parse_mode":"HTML"}, timeout=60)
        if r.status_code==200:
            logger.info(f"TG 200: {text[:60]}")
            return True
        logger.error(f"TG Error {r.status_code}")
        return False
    except Exception as e:
        logger.error(f"TG Error {e}")
        return False

@app.on_event("startup")
async def startup():
    logger.info(f"ALERTS WATCH 98: {total} tickers FULL - BOTH NOW PRESERVED")
    logger.info(f"98 Stocks 31/33/34 | Score 50 + Price + % | 08:30-16:00 NY 24h | BOTH NOW PR")
    send_tg("🚀 ALERTS BOT 98 STARTED\n98 Stocks | BOTH NOW PRESERVED")

@app.get("/")
async def root(): return {"status":"online","tickers":total,"file":L3_FILE,"note":"BOTH NOW PRESERVED"}
@app.get("/health")
async def health(): return {"ok":True,"tickers":total}
@app.get("/webhook")
async def webhook_get(): return {"status":"webhook alive - use POST"}
@app.post("/webhook")
async def webhook_post(req: Request):
    try: data = await req.json()
    except:
        body = await req.body()
        try: data = json.loads(body.decode())
        except: data={}
    ticker = data.get("ticker") or data.get("symbol") or "UNKNOWN"
    clean = ticker.split(":")[-1] if ":" in ticker else ticker
    msg = f"🔥 L3 ALERT: {clean}\nScore: {data.get('score','?')} {data.get('level','')}\nPrice: {data.get('price','')} RVOL: {data.get('rvol','')}"
    logger.info(f"L3 ALERT: {clean} {data}")
    ok = send_tg(msg)
    return JSONResponse({"status":"ok","ticker":clean,"telegram_sent":ok})
