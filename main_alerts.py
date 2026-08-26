"""
MODE DIRECT - FINAL 98 - NO TradingView needed
- 98 tickers 10 sectors BOTH NOW PRESERVED
- Scans every 5min NY 08:30-16:00 via Finnhub
"""
import os, json, requests, hashlib, time, pathlib, threading
from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
FINNHUB = os.getenv("FINNHUB_API_KEY", "")
PORT = int(os.getenv("PORT", "8000"))
BASE_DIR = pathlib.Path(__file__).parent

def load_L3():
    for p in [BASE_DIR/"L3_sectors.json", BASE_DIR/"watchlists"/"L3_sectors.json"]:
        if p.exists():
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                total = sum(len(v) for v in data.values())
                print(f"L3 DIRECT {total} tickers")
                return data
    return {}

L3_SECTORS = load_L3()
SECTOR_LINKS = {
    "SSD_Storage":["AI_Cooling","Controller_Chip","Chip_Mfg"],
    "AI_Cooling":["SSD_Storage","AI_Power","Chip_Mfg"],
    "AI_Power":["AI_Cooling","Controller_Chip","Chip_Mfg","Quantum"],
    "Controller_Chip":["Chip_Mfg","SSD_Storage","AI_Cooling"],
    "Chip_Mfg":["Controller_Chip","SSD_Storage","Optical"],
    "Optical":["Chip_Mfg","Space_Drones"],
    "SMR_Nuclear":["Energy_Metals","AI_Power"],
    "Energy_Metals":["SMR_Nuclear","AI_Power"],
    "Space_Drones":["Optical","Energy_Metals"],
    "Quantum":["AI_Power","Chip_Mfg"]
}

_last = {}; _seen=set()
def is_ny_session():
    try:
        ny = datetime.now(ZoneInfo("America/New_York"))
        if ny.weekday()>=5: return False
        hm = ny.hour*60+ny.minute
        return 510 <= hm <= 960
    except: return True

def can_send(k, mins=60):
    now=datetime.utcnow()
    if k in _last and now-_last[k] < timedelta(minutes=mins): return False
    _last[k]=now; return True

def is_dup(h):
    hd=hashlib.md5(h.encode()).hexdigest()
    if hd in _seen: return True
    _seen.add(hd)
    if len(_seen)>1000: _seen.clear()
    return False

def tg(text):
    if not TOKEN or not CHAT_ID: return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id":CHAT_ID,"text":text[:4000]}, timeout=15)
        print(f"TG {r.status_code}: {text[:80]}"); return True
    except Exception as e: print(e); return False

def get_news(ticker):
    if not FINNHUB: return []
    try:
        clean=ticker.split(":")[-1].replace(".V","").replace(".TO","")
        url=f"https://finnhub.io/api/v1/company-news?symbol={clean}&from={(datetime.utcnow()-timedelta(days=2)).strftime('%Y-%m-%d')}&to={datetime.utcnow().strftime('%Y-%m-%d')}&token={FINNHUB}"
        r=requests.get(url, timeout=10)
        if r.status_code==200:
            return [n for n in r.json()[:3] if n.get("headline")]
    except: pass
    return []

def scan_L3_direct():
    if not is_ny_session(): print("SKIP outside NY"); return
    total=sum(len(v) for v in L3_SECTORS.values())
    print(f"[{datetime.now()}] DIRECT SCAN {total} - 98 FULL")
    for sector, tickers in L3_SECTORS.items():
        for tv in tickers:
            plain=tv.split(":")[-1].replace(".V","").replace(".TO","")
            if not can_send(f"{sector}_{plain}",60): continue
            news=get_news(plain)
            if news and not is_dup(news[0]["headline"]):
                tg(f"🏭 DIRECT L3 {sector}\nTicker: {tv}\n{news[0]['headline']}\n{news[0].get('url','')}\nTotal 98 BOTH NOW")

scheduler=BackgroundScheduler()
scheduler.add_job(scan_L3_direct,'interval',minutes=5,id="L3_DIRECT")

def tg_poll():
    if not TOKEN: return
    offset=0
    tg(f"✅ DIRECT MODE 98 ONLINE\nBOTH NOW PRESERVED\nSSD:9 Energy:14 Optical:8 SMR:8 Space:9 Cooling:10 Power:17 Controller:8 Quantum:8 Chip:7\nScan 5min NY - NO TradingView")
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset":offset,"timeout":30}, timeout=35)
            for upd in r.json().get("result",[]):
                offset=upd["update_id"]+1
        except: time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    threading.Thread(target=tg_poll, daemon=True).start()
    yield
    scheduler.shutdown()

app=FastAPI(lifespan=lifespan)

@app.get("/")
def home():
    total=sum(len(v) for v in L3_SECTORS.values())
    return {"status":"online","mode":"DIRECT 98 NO TradingView","tickers":total,"both_now":True,"sectors":{k:len(v) for k,v in L3_SECTORS.items()},"ny":is_ny_session()}

@app.post("/webhook")
async def webhook(req: Request):
    data=await req.json()
    ticker=data.get("ticker","").split(":")[-1]
    if not is_ny_session(): return {"status":"skipped","reason":"outside NY"}
    tg(f"🔥 ALERT DIRECT: {ticker} - 98 FULL")
    return {"ok":True}

if __name__=="__main__":
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=PORT)
