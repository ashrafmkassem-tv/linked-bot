"""
PREPARE BOT - 98 STOCKS - ENGLISH ONLY - NO REPEAT - MARKET HOURS ONLY
- 9:00 AM to 4:00 PM ET Mon-Fri only, pre-market 30min, no weekend, not 24h
- PREPARE mode: catch flat 0% before fly, not after +1% +2%
- No Arabic, no repeat 90min + hash dedup
- Stop 3.5% tight
"""
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
        if now.weekday() >= 5: # Sat=5 Sun=6
            return False
        start = now.replace(hour=9, minute=0, second=0, microsecond=0) # 30min pre-market
        end = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return start <= now <= end
    except:
        now = datetime.utcnow()
        if now.weekday() >= 5: return False
        mins = now.hour*60+now.minute
        return 13*60 <= mins <= 20*60

BASE_DIR = pathlib.Path(__file__).parent
def load_sectors():
    for p in [BASE_DIR/"L3_sectors.json", BASE_DIR/"watchlists"/"L3_sectors.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict) and all(isinstance(v,list) for v in data.values()):
                    return data
            except: pass
    return {}

L3_SECTORS = load_sectors()
all_tvs = [t for lst in L3_SECTORS.values() for t in lst]
WATCH_98 = sorted(list(set([tv.split(":")[-1].replace(".V","").replace(".TO","").upper() for tv in all_tvs])))
print(f"PREPARE BOT 98 FULL - MARKET 9:00-16:00 ET ONLY - {len(WATCH_98)} tickers - BOTH NOW")

_last = {}
_seen = set()
def can_send(k, mins=90):
    now = datetime.utcnow()
    if k in _last and now-_last[k] < timedelta(minutes=mins): return False
    _last[k]=now
    return True

def is_dup(txt):
    h=hashlib.md5(txt.encode()).hexdigest()
    if h in _seen: return True
    _seen.add(h)
    if len(_seen)>1000: _seen.clear()
    return False

def tg(text, cid=None):
    c=cid or CHAT_ID
    if not TOKEN or not c: return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id":c,"text":text[:4000],"disable_web_page_preview":True}, timeout=10)
    except Exception as e:
        print(f"TG error {e}")

def get_candles(sym, days=80):
    if not FINNHUB: return None
    try:
        to_ts=int(datetime.utcnow().timestamp())
        from_ts=int((datetime.utcnow()-timedelta(days=days)).timestamp())
        r=requests.get(f"https://finnhub.io/api/v1/stock/candle?symbol={sym}&resolution=D&from={from_ts}&to={to_ts}&token={FINNHUB}", timeout=12)
        d=r.json()
        if d.get("s")!="ok" or not d.get("c"): return None
        return d
    except: return None

def sma(p,n): return sum(p[-n:])/n if len(p)>=n else None
def ema(p,n):
    if len(p)<n: return None
    k=2/(n+1); e=sum(p[:n])/n
    for x in p[n:]: e=x*k+e*(1-k)
    return e
def rsi(p,n=14):
    if len(p)<n+1: return 50
    g=l=0
    for i in range(1,n+1):
        d=p[-i]-p[-i-1]
        if d>0: g+=d
        else: l-=d
    if l==0: return 100
    return 100-(100/(1+g/l))
def bb_width(p,n=20):
    s=sma(p,n)
    if not s: return None
    var=sum((x-s)**2 for x in p[-n:])/n
    return (4*math.sqrt(var))/s

def get_sector(tick):
    for sec,lst in L3_SECTORS.items():
        if tick in [x.split(":")[-1].replace(".V","").replace(".TO","").upper() for x in lst]:
            return sec
    return None

def analyze_prepare(ticker):
    d=get_candles(ticker,80)
    if not d or len(d["c"])<30: return None
    c=d["c"]; v=d["v"]
    price=c[-1]
    pct=(c[-1]-c[-2])/c[-2]*100 if c[-2]!=0 else 0
    if not (-0.8 <= pct <= 0.8): return None # flat only, not +1% +2%
    e9=ema(c,9); e21=ema(c,21); s20=sma(c,20)
    r=rsi(c,14); bb=bb_width(c,20)
    if not all([e9,e21,s20,bb]): return None
    rvol=v[-1]/(sum(v[-21:-1])/20) if sum(v[-21:-1])!=0 else 1
    if not (0.02 <= bb <= 0.09): return None
    if not (46 <= r <= 59): return None
    if not (0.7 <= rvol <= 1.6): return None
    if abs(e9-e21)/price > 0.015: return None
    if abs(price-s20)/s20 > 0.025: return None
    score=0
    if 50<=r<=56: score+=30
    if bb<0.06: score+=30
    elif bb<0.08: score+=20
    if 1.0<=rvol<=1.5: score+=25
    if e9>e21: score+=15
    if score>=60:
        return {"sym":ticker,"price":price,"pct":pct,"score":score,"rsi":r,"rvol":rvol,"bb":bb,
                "entry_low":price*0.992,"entry_high":price*1.008,"stop":price*0.965,"t1":price*1.08,"t2":price*1.18,
                "sector":get_sector(ticker)}
    return None

scheduler=BackgroundScheduler()
def scan_prepare():
    if not is_market_open():
        print(f"CLOSED {datetime.now(ET_TZ)}")
        return
    for t in WATCH_98:
        if not can_send(f"PREP_{t}",90): continue
        res=analyze_prepare(t)
        if not res: continue
        msg=(f"PREPARE: {res['sym']} ${res['price']:.2f} {res['pct']:+.2f}% Score {res['score']}/100\n"
             f"Setup: BB {res['bb']:.3f} RSI {res['rsi']:.0f} rVol {res['rvol']:.1f}x EMA 9/21 compressed Sector {res['sector']}\n"
             f"State: Still flat, preparing to move - catch from start\n"
             f"Entry: ${res['entry_low']:.2f}-${res['entry_high']:.2f} Stop: ${res['stop']:.2f} (3.5%)\n"
             f"Target: ${res['t1']:.2f} / ${res['t2']:.2f}")
        if is_dup(msg): continue
        tg(msg)
        time.sleep(1)

scheduler.add_job(scan_prepare,'interval',minutes=2,id="PREP")

def handle_telegram():
    if not TOKEN: return
    offset=0
    tg(f"PREPARE BOT STARTED - 98 stocks - 9:00-16:00 ET only - English only - No repeat 90min - Stop 3.5% - Catch before fly")
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset":offset,"timeout":30}, timeout=35)
            d=r.json()
            if not d.get("ok"): time.sleep(5); continue
            for u in d.get("result",[]):
                offset=u["update_id"]+1
                msg=u.get("message") or u.get("edited_message")
                if not msg: continue
                text=msg.get("text","").strip()
                if not text: continue
                low=text.lower(); cid=msg["chat"]["id"]
                if low.startswith("/start"):
                    tg(f"PREPARE BOT - {len(WATCH_98)} stocks\nMarket: 9:00-16:00 ET Mon-Fri only\nCommands: /analyze TICKER, /scan", cid)
                elif low.startswith("/scan"):
                    tg("Scanning 98 prepare...", cid)
                    scan_prepare()
                elif low.startswith("/analyze"):
                    parts=text.split()
                    if len(parts)>=2:
                        tk=parts[1].upper()
                        tg(f"Analyzing {tk} prepare...", cid)
                        res=analyze_prepare(tk)
                        if res:
                            tg(f"PREPARE {res['sym']} ${res['price']:.2f} {res['pct']:+.2f}% Score {res['score']} BB {res['bb']:.3f} RSI {res['rsi']:.0f} rVol {res['rvol']:.1f}x Entry ${res['entry_low']:.2f}-${res['entry_high']:.2f} Stop ${res['stop']:.2f}", cid)
                        else:
                            tg(f"{tk} not in prepare state - already moved or not ready", cid)
        except Exception as e:
            print(f"TG error {e}"); time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running: scheduler.start()
    t=threading.Thread(target=handle_telegram, daemon=True); t.start()
    yield
    scheduler.shutdown()

app=FastAPI(title="PREPARE 98 - 9-16 ET only", lifespan=lifespan)
@app.get("/")
def home(): return {"status":"PREPARE 98","market":"OPEN" if is_market_open() else "CLOSED","time_et":str(datetime.now(ET_TZ)),"watch":len(WATCH_98)}
@app.get("/health")
def health(): return {"ok":True,"market_open":is_market_open(),"watch":len(WATCH_98)}
@app.post("/webhook/ai")
async def webhook_ai(req: Request):
    try: data=await req.json()
    except: data={}
    if not is_market_open(): return {"market_closed":1}
    ticker=(data.get("ticker","").split(":")[-1] or data.get("symbol","").split(":")[-1]).upper()
    if not ticker: return {"error":"no ticker"}
    if not can_send(f"TV_{ticker}",30): return {"cooldown":1}
    res=analyze_prepare(ticker)
    if not res: return {"ok":True,"no_prepare":1}
    msg=f"PREPARE TV {ticker} ${res['price']:.2f} Score {res['score']} BB {res['bb']:.3f} Entry ${res['entry_low']:.2f}-${res['entry_high']:.2f} Stop ${res['stop']:.2f}"
    if not is_dup(msg): tg(msg)
    return {"ok":True}
@app.post("/webhook/tradingview")
async def webhook_tv(req: Request):
    return await webhook_ai(req)
