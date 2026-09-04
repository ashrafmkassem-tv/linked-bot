# DIRECT MODE ONLY - NO TRADINGVIEW - V3 FIXED FOR RAILWAY
# Fixes: Loads L3 from multiple paths, never silent on empty list, manual /scan bypasses market hours, better Finnhub retry
# PREPARE logic: flat -0.8% to +0.8%, Score 65, BB 0.05, RSI 53, rVol 1.2x, Stop 3.5%
# BUY/SELL direct from Railway - Both read L3 json

import os, json, requests, time, pathlib, threading, math
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN_ALERTS", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID_ALERTS", "")
FINNHUB = os.getenv("FINNHUB_API_KEY_ALERTS", os.getenv("FINNHUB_API_KEY", ""))
PORT = int(os.getenv("PORT", "8000"))

BASE_DIR = pathlib.Path(__file__).parent
ET_ZONE = ZoneInfo("America/New_York")

def load_sectors():
    # Try all possible locations/names
    candidates = [
        BASE_DIR/"L3_sectors.json",
        BASE_DIR/"L3_sectors_FINAL.json",
        BASE_DIR/"data"/"L3_sectors.json",
        pathlib.Path("/mnt/data/L3_sectors.json"),
        pathlib.Path("/mnt/data/L3_sectors_FINAL.json"),
        pathlib.Path("/app/L3_sectors.json"),
        pathlib.Path("/app/L3_sectors_FINAL.json"),
    ]
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict) and all(isinstance(v,list) for v in data.values()):
                    print(f"[OK] Loaded sectors from {p} -> {sum(len(v) for v in data.values())} tickers")
                    return data
            except Exception as e:
                print(f"[ERR] Failed to load {p}: {e}")
    print("[WARN] No L3_sectors file found, returning empty")
    return {}

L3_SECTORS = load_sectors()
all_tvs = [t for lst in L3_SECTORS.values() for t in lst]
WATCH_LIST = sorted(set([t.split(":")[-1].replace(".V","").replace(".TO","").upper() for t in all_tvs]))
WATCH_98 = WATCH_LIST

# Fallback if empty - use FINAL embedded list to never stay silent
if not WATCH_LIST:
    try:
        fallback_path = pathlib.Path(__file__).parent / "L3_sectors_FINAL.json"
        if not fallback_path.exists():
            fallback_path = pathlib.Path("/mnt/data/L3_sectors_FINAL.json")
        if fallback_path.exists():
            data = json.loads(fallback_path.read_text())
            all_tvs = [t for lst in data.values() for t in lst]
            WATCH_LIST = sorted(set([t.split(":")[-1].replace(".V","").replace(".TO","").upper() for t in all_tvs]))
            WATCH_98 = WATCH_LIST
            L3_SECTORS = data
            print(f"[FALLBACK] Loaded {len(WATCH_LIST)} tickers from {fallback_path}")
    except Exception as e:
        print(f"[FALLBACK ERR] {e}")

print(f"DIRECT SCAN {len(WATCH_LIST)} - {len(WATCH_LIST)} tickers - RIG present: {'RIG' in WATCH_LIST}")

_last = {}
def can_send(k, mins=90):
    now = datetime.now(ET_ZONE)
    if k in _last and now - _last[k] < timedelta(minutes=mins): return False
    _last[k]=now
    return True

def is_market_hours():
    now_et = datetime.now(ET_ZONE)
    if now_et.weekday() > 4: return False
    start = now_et.replace(hour=9, minute=0, second=0, microsecond=0)
    end = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return start <= now_et <= end

def tg(text):
    if not TOKEN or not CHAT_ID:
        print(f"[SKIP TG NOT CONFIGURED] {text[:100]}"); return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          json={"chat_id":CHAT_ID,"text":text[:4000],"disable_web_page_preview":True}, timeout=10)
        print(f"[ALERT {r.status_code}] {text[:120]}")
        return r.status_code==200
    except Exception as e:
        print(f"TG Error {e}"); return False

def get_candles(sym, days=80):
    if not FINNHUB: 
        print("[ERR] FINNHUB key missing")
        return None
    try:
        clean = sym.split(":")[-1].replace(".V","").replace(".TO","").upper()
        to_ts = int(datetime.now(ZoneInfo("UTC")).timestamp())
        from_ts = int((datetime.now(ZoneInfo("UTC"))-timedelta(days=days)).timestamp())
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={clean}&resolution=D&from={from_ts}&to={to_ts}&token={FINNHUB}"
        r=requests.get(url, timeout=12)
        if r.status_code == 429:
            print(f"[FINNHUB 429 Rate Limit] {clean} - sleeping 2s")
            time.sleep(2)
            return None
        if r.status_code!=200: 
            print(f"[FINNHUB {r.status_code}] {clean}")
            return None
        d=r.json()
        if d.get("s")!="ok" or not d.get("c"): return None
        return {"c":d["c"],"v":d["v"]}
    except Exception as e:
        print(f"[CANDLE ERR] {sym}: {e}")
        return None

def rsi_calc(prices,per=14):
    if len(prices)<per+1: return 50
    g=l=0
    for i in range(1,per+1):
        diff=prices[-i]-prices[-i-1]
        if diff>0: g+=diff
        else: l-=diff
    if l==0: return 100
    return 100-(100/(1+g/l))

def bollinger(prices,per=20):
    if len(prices)<per: return None
    s=sum(prices[-per:])/per
    var=sum((x-s)**2 for x in prices[-per:])/per
    std=math.sqrt(var)
    up=s+2*std; lo=s-2*std
    width=(up-lo)/s if s!=0 else 0
    pct=(prices[-1]-lo)/(up-lo) if up!=lo else 0.5
    return {"width":width,"pct":pct}

def rvol_calc(vols,per=20):
    if len(vols)<per+1: return 1.0
    avg=sum(vols[-per-1:-1])/per
    return vols[-1]/avg if avg!=0 else 1.0

def analyze_prepare(ticker):
    daily=get_candles(ticker,80)
    if not daily or len(daily["c"])<20: return None
    c=daily["c"]; v=daily["v"]
    price=c[-1]; prev=c[-2]
    chg=(price-prev)/prev*100 if prev!=0 else 0
    if not (-0.8 <= chg <= 0.8): return None
    rsi=rsi_calc(c); bb=bollinger(c); rv=rvol_calc(v)
    if not bb: return None
    score=0
    if -0.8 <= chg <= 0.8: score+=30
    if 50 <= rsi <= 56: score+=25
    elif 48 <= rsi <= 60: score+=20
    if bb["width"] <= 0.05: score+=25
    elif bb["width"] <= 0.08: score+=15
    if rv >= 1.2: score+=15
    if score<65: return None
    return {"symbol":ticker,"price":price,"chg":chg,"score":score,"rsi":rsi,"rvol":rv,"bb":bb["width"],"stop":price*0.965,"t1":price*1.18,"t2":price*1.35}

scheduler=BackgroundScheduler()

def direct_scan_98(bypass_market=False):
    WATCH = WATCH_LIST
    now_et=datetime.now(ET_ZONE)
    ts=now_et.strftime("%Y-%m-%d %H:%M:%S")
    if not WATCH:
        print(f"[{ts} ET] DIRECT SCAN 0 - EMPTY WATCH LIST! Check L3_sectors.json")
        tg(f"⚠️ ALERTS WARNING: WATCH LIST EMPTY at {ts} ET - Check L3_sectors.json in Railway")
        return
    if not bypass_market and not is_market_hours():
        print(f"[{ts} ET] DIRECT SCAN {len(WATCH)} - Skip outside 09:00-16:00 ET Mon-Fri")
        return
    print(f"[{ts} ET] DIRECT SCAN {len(WATCH)} - START {len(WATCH)} FULL BOTH NOW")
    found=0
    for t in WATCH:
        try:
            res=analyze_prepare(t)
            if not res: 
                time.sleep(0.2); continue
            key=f"PREPARE_{res['symbol']}"
            if not can_send(key,90): continue
            found+=1
            msg=(f"🟢 BUY PREPARE: {res['symbol']} ${res['price']:.2f} ({res['chg']:+.2f}%) Score {res['score']}/100\n"
                 f"Flat -0.8 to +0.8% | RSI {res['rsi']:.1f} | rVol {res['rvol']:.2f}x | BB {res['bb']:.3f}\n"
                 f"Entry ${res['price']:.2f} Target ${res['t1']:.2f} / ${res['t2']:.2f} Stop ${res['stop']:.2f} (3.5%)")
            tg(msg)
            time.sleep(0.5)
        except Exception as e:
            print(f"Scan err {t}: {e}")
    print(f"[{ts} ET] DIRECT SCAN {len(WATCH)} - Done Found {found} - {len(WATCH)} FULL BOTH NOW")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.add_job(lambda: direct_scan_98(False),'interval',minutes=5,id='scan98')
        scheduler.start()
        print(f"Scheduler DIRECT SCAN {len(WATCH_98)} every 5min - 09:00-16:00 ET only - NO TradingView")
        # Send startup message
        tg(f"✅ Linked-Bot Started: {len(WATCH_98)} tickers loaded - {datetime.now(ET_ZONE).strftime('%Y-%m-%d %H:%M ET')}")
    yield
    scheduler.shutdown()

app=FastAPI(title=f"DIRECT {len(WATCH_LIST) if 'WATCH_LIST' in dir() else 0} PREPARE - No TV", lifespan=lifespan)

@app.get("/")
def home():
    return {"status":f"DIRECT {len(WATCH_98)} PREPARE {len(WATCH_98)} - 09:00-16:00 ET Mon-Fri - No TradingView","market_open":is_market_hours(),"et_now":datetime.now(ET_ZONE).isoformat(), "watch_count": len(WATCH_98)}

@app.get("/health")
def health():
    return {"ok":True,"count":len(WATCH_LIST),"market_open":is_market_hours(),"rig":"RIG" in WATCH_LIST, "tickers": WATCH_LIST, "last_alerts": list(_last.keys())[-10:]}

@app.get("/scan")
def manual():
    threading.Thread(target=lambda: direct_scan_98(True),daemon=True).start()
    return {"started":f"DIRECT SCAN {len(WATCH_98)} - bypass market hours"}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=PORT)
