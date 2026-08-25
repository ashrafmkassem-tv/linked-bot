import os
import json
import logging
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="L3 98 Alerts Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    logger.error(f"Failed to load {L3_FILE}: {e}")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram env not set")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=60)
        if r.status_code == 200:
            logger.info(f"TG 200: {text[:80]}")
            return True
        else:
            logger.error(f"TG Error {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"TG Error {e}")
        return False

@app.on_event("startup")
async def startup():
    logger.info(f"ALERTS WATCH 98: {total} tickers FULL - BOTH NOW PRESERVED - 50 SCORE - 0830-1600 NY")
    logger.info(f"98 Stocks 31/33/34 | Score 50 + Price + % | 08:30-16:00 NY 24h | BOTH NOW PR")
    send_telegram("🚀 ALERTS BOT 98 STARTED\n98 Stocks | Score 50 + Price + % | 08:30-16:00 NY 24h | BOTH NOW PRESERVED")

@app.get("/")
async def root():
    return {"status": "online", "tickers": total, "file": L3_FILE, "note": "BOTH NOW PRESERVED - 98 FULL", "sectors": {k: len(v) for k, v in sectors.items()}}

@app.get("/health")
async def health():
    return {"ok": True, "tickers": total}

@app.get("/webhook")
async def webhook_get():
    return {"status": "webhook alive - use POST", "example": {"ticker": "SOFI", "score": 80, "level": "PRE_85"}}

@app.post("/webhook")
async def webhook_post(request: Request):
    try:
        data = await request.json()
    except:
        try:
            body = await request.body()
            data = json.loads(body.decode() if body else "{}")
        except:
            data = {}
    
    ticker = data.get("ticker") or data.get("symbol") or "UNKNOWN"
    clean = ticker.split(":")[-1] if ":" in ticker else ticker
    score = data.get("score", "?")
    level = data.get("level", "")
    price = data.get("price", "")
    rvol = data.get("rvol", "")

    msg = f"🔥 L3 ALERT: {clean}\nScore: {score} {level}\nPrice: {price} RVOL: {rvol}\nNY: {datetime.now().strftime('%H:%M')}"

    logger.info(f"L3 ALERT: {ticker} {score} {level} data={data}")
    ok = send_telegram(msg)

    return JSONResponse({"status": "ok", "ticker": clean, "telegram_sent": ok, "received": data})
