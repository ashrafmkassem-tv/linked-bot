# DIRECT MODE ONLY - NO TRADINGVIEW - V2 Alpha PREPARE
# 98 tickers FULL BOTH NOW - 09:00-16:00 ET Mon-Fri only (30min pre-market to close)
# PREPARE logic: flat -0.8% to +0.8%, Score 65, BB 0.05, RSI 53, rVol 1.2x, Stop 3.5%
# Anti-duplicate 90min cooldown - Alerts line verified

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
    for p in [BASE_DIR/"L3_sectors.json", pathlib.Path("/mnt/data/L3_sectors.json")]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict) and all(isinstance(v,list) for v in data.values()):
                    return data
            except: pass
    return {}

L3_SECTORS = load_sectors()
all_tvs = [t for lst in L3_SECTORS.values() for t in lst]
WATCH_98 = sorted(set([t.split(":")[-1].replace(".V","").replace(".TO","").upper() for t in all_tvs]))
print(f"DIRECT SCAN 98 - {len(WATCH_98)} tickers - RIG present: {'RIG' in WATCH_98}")

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
        print(f"[SKIP] {text[:100]}"); return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          json={"chat_id":CHAT_ID,"text":text[:4000],"disable_web_page_preview":True}, timeout=10)
        print(f"[ALERT {r.status_code}] {text[:120]}")
        return r.status_code==200
    except Exception as e:
        print(f"TG Error {e}"); return False

def get_candles(sym, days=80):
    if not FINNHUB: return None
    try:
        clean = sym.split(":")[-1].replace(".V","").replace(".TO","").upper()
        to_ts = int(datetime.now(ZoneInfo("UTC")).timestamp())
        from_ts = int((datetime.now(ZoneInfo("UTC"))-timedelta(days=days)).timestamp())
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={clean}&resolution=D&from={from_ts}&to={to_ts}&token={FINNHUB}"
        r=requests.get(url, timeout=12)
        if r.status_code!=200: return None
        d=r.json()
        if d.get("s")!="ok" or not d.get("c"): return None
        return {"c":d["c"],"v":d["v"]}
    except: return None

def ema(prices,p):
    if len(prices)<p: return None
    k=2/(p+1); e=sum(prices[:p])/p
    for x in prices[p:]: e=x*k+e*(1-k)
    return e

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

def direct_scan_98():
    now_et=datetime.now(ET_ZONE)
    ts=now_et.strftime("%Y-%m-%d %H:%M:%S")
    if not is_market_hours():
        print(f"[{ts} ET] DIRECT SCAN 98 - Skip outside 09:00-16:00 ET Mon-Fri")
        return
    print(f"[{ts} ET] DIRECT SCAN 98 - START 98 FULL BOTH NOW")
    found=0
    for t in WATCH_98:
        try:
            res=analyze_prepare(t)
            if not res: time.sleep(0.2); continue
            key=f"PREPARE_{res['symbol']}"
            if not can_send(key,90): continue
            found+=1
            msg=(f"PREPARE: {res['symbol']} ${res['price']:.2f} ({res['chg']:+.2f}%) Score {res['score']}/100\n"
                 f"Flat -0.8 to +0.8% | RSI {res['rsi']:.1f} | rVol {res['rvol']:.2f}x | BB {res['bb']:.3f}\n"
                 f"Entry ${res['price']:.2f} Target ${res['t1']:.2f} / ${res['t2']:.2f} Stop ${res['stop']:.2f} (3.5%)")
            tg(msg)
            time.sleep(0.5)
        except Exception as e:
            print(f"Scan err {t}: {e}")
    print(f"[{ts} ET] DIRECT SCAN 98 - Done Found {found} - 98 FULL BOTH NOW")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.add_job(direct_scan_98,'interval',minutes=5,id='scan98')
        scheduler.start()
        print("Scheduler DIRECT SCAN 98 every 5min - 09:00-16:00 ET only - NO TradingView")
    yield
    scheduler.shutdown()

app=FastAPI(title="DIRECT 98 PREPARE - No TV", lifespan=lifespan)

@app.get("/")
def home():
    return {"status":f"DIRECT 98 PREPARE {len(WATCH_98)} - 09:00-16:00 ET Mon-Fri - No TradingView","market_open":is_market_hours(),"et_now":datetime.now(ET_ZONE).isoformat()}

@app.get("/health")
def health():
    return {"ok":True,"count":len(WATCH_98),"market_open":is_market_hours(),"rig":"RIG" in WATCH_98}

@app.get("/scan")
def manual():
    threading.Thread(target=direct_scan_98,daemon=True).start()
    return {"started":"DIRECT SCAN 98"}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=PORT)
