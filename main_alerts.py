import os, json, requests, time, pathlib, threading, math, hashlib
from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN_ALERTS", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID_ALERTS", "")
FINNHUB = os.getenv("FINNHUB_API_KEY_ALERTS", os.getenv("FINNHUB_API_KEY", ""))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET_ALERTS", "mysecret123")
PORT = int(os.getenv("PORT", "8000"))

ET_TZ = ZoneInfo("America/New_York")

def is_market_open():
    try:
        now = datetime.now(ET_TZ)
        if now.weekday() >= 5: # Sat Sun closed
            return False
        # 9:00 AM to 4:00 PM ET - 30 min pre-market
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return start <= now <= end
    except:
        now = datetime.utcnow()
        if now.weekday() >= 5: return False
        return (13*60) <= (now.hour*60+now.minute) <= (20*60)

BASE_DIR = pathlib.Path(__file__).parent
def load_sectors():
    for p in [BASE_DIR/"L3_sectors.json", BASE_DIR/"watchlists"/"L3_sectors.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict) and all(isinstance(v,list) for v in data.values()): return data
            except: pass
    return {}

L3_SECTORS = load_sectors()
all_tvs = [t for lst in L3_SECTORS.values() for t in lst]
WATCH_98 = sorted(list(set([tv.split(":")[-1].replace(".V","").replace(".TO","").upper() for tv in all_tvs])))
print(f"PREPARE BOT 98 - MARKET 9:00-16:00 ET ONLY - {len(WATCH_98)} tickers")

_last = {}
_seen_hash = set()
def can_send(k, mins=90):
    now = datetime.utcnow()
    if k in _last and now - _last[k] < timedelta(minutes=mins): return False
    _last[k] = now
    return True

def is_dup(text):
    h = hashlib.md5(text.encode()).hexdigest()
    if h in _seen_hash: return True
    _seen_hash.add(h)
    if len(_seen_hash) > 1000: _seen_hash.clear()
    return False

def tg(text, chat_id=None):
    if not TOKEN or not (chat_id or CHAT_ID): return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id or CHAT_ID, "text": text[:4000], "disable_web_page_preview": True}, timeout=10)
    except: pass

def get_candles(sym, days=80):
    if not FINNHUB: return None
    try:
        to_ts = int(datetime.utcnow().timestamp())
        from_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        r = requests.get(f"https://finnhub.io/api/v1/stock/candle?symbol={sym}&resolution=D&from={from_ts}&to={to_ts}&token={FINNHUB}", timeout=12)
        d = r.json()
        if d.get("s")!= "ok" or not d.get("c"): return None
        return d
    except: return None

def sma(p, n): return sum(p[-n:])/n if len(p)>=n else None
def ema(p, n):
    if len(p)<n: return None
    k=2/(n+1); e=sum(p[:n])/n
    for x in p[n:]: e=x*k+e*(1-k)
    return e
def rsi(p, n=14):
    if len(p)<n+1: return 50
    g=l=0
    for i in range(1,n+1):
        d=p[-i]-p[-i-1]
        if d>0: g+=d
        else: l-=d
    if l==0: return 100
    return 100-(100/(1+g/l))
def bb_width(p, n=20):
    s=sma(p,n)
    if not s: return None
    var=sum((x-s)**2 for x in p[-n:])/n
    return (2*math.sqrt(var)*2)/s if s else None

def analyze_prepare(ticker):
    d=get_candles(ticker, 80)
    if not d or len(d["c"])<30: return None
    c=d["c"]; v=d["v"]
    price=c[-1]
    pct_today = (c[-1]-c[-2])/c[-2]*100 if c[-2]!=0 else 0

    # MUST be flat, not already +1% or +2%
    if not (-0.8 <= pct_today <= 0.8): return None

    e9=ema(c,9); e21=ema(c,21); s20=sma(c,20)
    r=rsi(c,14); bb=bb_width(c,20)
    if not all([e9,e21,s20,bb]): return None
    rvol = (v[-1]/(sum(v[-21:-1])/20)) if sum(v[-21:-1])!=0 else 1

    # PREPARE filters - before fly
    if not (0.02 <= bb <= 0.09): return None # squeeze
    if not (46 <= r <= 59): return None # not pumped
    if not (0.7 <= rvol <= 1.6): return None # building, not exploded
    if abs(e9-e21)/price > 0.015: return None # EMAs compressed
    if abs(price-s20)/s20 > 0.025: return None # close to SMA20

    score=0
    if 50<=r<=56: score+=30
    if bb<0.06: score+=30
    elif bb<0.08: score+=20
    if 1.0<=rvol<=1.5: score+=25
    if e9>e21: score+=15

    if score>=60:
        return {"sym":ticker,"price":price,"score":score,"rsi":r,"rvol":rvol,"bb":bb,"pct":pct_today,
                "entry_low":price*0.992,"entry_high":price*1.008,"stop":price*0.965,"t1":price*1.08,"t2":price*1.18}

scheduler=BackgroundScheduler()
def scan_prepare():
    if not is_market_open():
        print(f"Market CLOSED {datetime.now(ET_TZ)}")
        return
    for t in WATCH_98:
        if not can_send(f"PREP_{t}", 90): continue
        res=analyze_prepare(t)
        if not res: continue
        msg=(f"PREPARE: {res['sym']} ${res['price']:.2f} {res['pct']:+.2f}% Score {res['score']}/100\n"
             f"Setup: BB {res['bb']:.3f} RSI {res['rsi']:.0f} rVol {res['rvol']:.1f}x EMA 9/21 compressed\n"
             f"State: Still flat, preparing to move - catch from start\n"
             f"Entry: ${res['entry_low']:.2f}-${res['entry_high']:.2f} Stop: ${res['stop']:.2f} (3.5%)\n"
             f"Target: ${res['t1']:.2f} / ${res['t2']:.2f}")
        if is_dup(msg): continue
        tg(msg)
        time.sleep(1)

scheduler.add_job(scan_prepare, 'interval', minutes=2, id="PREP")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running: scheduler.start()
    yield
    scheduler.shutdown()

app=FastAPI(lifespan=lifespan)
@app.get("/")
def home(): return {"market": "OPEN" if is_market_open() else "CLOSED", "time_et": str(datetime.now(ET_TZ)), "watch": len(WATCH_98)}
@app.get("/health")
def health(): return {"ok":True,"market_open":is_market_open()}
