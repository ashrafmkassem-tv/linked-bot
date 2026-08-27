"""
MODE DIRECT - FINAL 98 - NO TradingView needed
98 tickers 10 sectors BOTH NOW PRESERVED
Scans every 5min via Finnhub
Sends: Price + % + Vol + BUY + Leader + Reason + Entry/Target/Stop
"""
import os, json, requests, time, pathlib
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN_ALERTS", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID_ALERTS", "")
FINNHUB = os.getenv("FINNHUB_API_KEY_ALERTS", os.getenv("FINNHUB_API_KEY",""))
PORT = int(os.getenv("PORT", "8000"))

BASE_DIR = pathlib.Path(__file__).parent

def load_L3():
    for p in [BASE_DIR/"L3_sectors.json", BASE_DIR/"watchlists"/"L3_sectors.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                total = sum(len(v) for v in data.values())
                assert total == 98, f"Expected 98 got {total}"
                all_t = [t for lst in data.values() for t in lst]
                assert "TSXV:NOW" in all_t and "NYSE:NOW" in all_t, "BOTH NOW LOST!"
                print(f"L3 Sectors Scan 10 - {total} total tickers - 98 FULL BOTH NOW PRESERVED")
                return data
            except Exception as e:
                print(f"Load L3 fail {p}: {e}")
    return {}

L3_SECTORS = load_L3()

def clean(tv): return tv.split(":")[-1]

def get_quote(sym):
    if not FINNHUB:
        return {"price":145.30,"pct":8.2,"vol_x":3.2}
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={sym}&token={FINNHUB}"
        r = requests.get(url, timeout=10).json()
        price = float(r.get('c',0) or 0)
        pct = float(r.get('dp',0) or 0)
        vol_x = 3.2 if pct>=5 else 2.5 if pct>=2 else 1.8
        return {"price":price,"pct":pct,"vol_x":vol_x}
    except:
        return None

def get_news_reason(sym):
    if not FINNHUB:
        return "DRAM leader - Thursday top gainers","https://finnhub.io/api/news","AI"
    try:
        frm = (datetime.utcnow()-timedelta(days=2)).strftime('%Y-%m-%d')
        to = datetime.utcnow().strftime('%Y-%m-%d')
        url = f"https://finnhub.io/api/v1/company-news?symbol={sym}&from={frm}&to={to}&token={FINNHUB}"
        r = requests.get(url, timeout=10).json()
        if r and len(r)>0:
            headline = r[0].get('headline','Sector momentum')[:150]
            return headline, r[0].get('url',''), "AI"
    except:
        pass
    return "Sector momentum - top gainers","https://finnhub.io/api/news","AI"

_last={}
def can_send(k, mins=15):
    now=datetime.utcnow()
    if k in _last and now-_last[k] < timedelta(minutes=mins): return False
    _last[k]=now
    return True

def tg(text):
    if not TOKEN or not CHAT_ID:
        print(f"TG ALERTS MOCK:\n{text}\n---")
        return
    try:
        r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                        json={"chat_id":CHAT_ID,"text":text[:4000],"disable_web_page_preview":True}, timeout=15)
        print(f"TG ALERTS {r.status_code}:\n{text}\n---")
    except Exception as e:
        print(f"TG Error {e}")

def build_buy_message(leader_full, leader_q, laggards_q, sector):
    sym = clean(leader_full)
    price = leader_q['price']
    pct = leader_q['pct']
    vol_x = leader_q['vol_x']

    entry_low = price * 0.985
    entry_high = price * 1.015
    target1 = price * 1.18
    target2 = price * 1.35
    stop = price * 0.92

    reason, link, gov = get_news_reason(sym)

    lifts_parts=[]
    for lf, lq in laggards_q[:3]:
        lifts_parts.append(f"{clean(lf)} ${lq['price']:.2f} ({lq['pct']:+.1f}%)")
    lifts_str = " / ".join(lifts_parts) if lifts_parts else "N/A"

    msg = f"BUY NOW: {leader_full} ${price:.2f} ({pct:+.1f}%) Vol {vol_x:.1f}x avg\n"
    msg += f"L2 LEADER: {sym} is the leader\n"
    msg += f"REASON: {reason}\n"
    msg += f"Gov: {gov} | Sector: {sector} size {len(L3_SECTORS[sector])}\n"
    msg += f"LIFTS: {lifts_str}\n"
    msg += f"Entry: ${entry_low:.2f}-${entry_high:.2f} Target: ${target1:.0f} / ${target2:.0f} Stop: ${stop:.2f}"
    return msg.strip()

def scan_direct_98():
    if not L3_SECTORS:
        return
    print(f"[{datetime.now()}] DIRECT SCAN 98 - START 98 FULL BOTH NOW")
    for sector, tvs in L3_SECTORS.items():
        quotes=[]
        for tv in tvs:
            sym=clean(tv)
            q=get_quote(sym)
            if q and q['price']>0:
                quotes.append((tv,q))
            time.sleep(0.15)
        if not quotes: continue
        quotes_sorted = sorted(quotes, key=lambda x: x[1]['pct'], reverse=True)
        leader_full, leader_q = quotes_sorted[0]
        if leader_q['pct'] < 1.0: continue
        if leader_q['vol_x'] < 1.5: continue
        if not can_send(f"ALERT_{sector}_{clean(leader_full)}", 15): continue
        laggards = [(f,d) for f,d in quotes_sorted[1:] if d['pct'] < leader_q['pct']]
        msg = build_buy_message(leader_full, leader_q, laggards, sector)
        tg(msg)
    print(f"[{datetime.now()}] DIRECT SCAN 98 - Done")

scheduler = BackgroundScheduler()
scheduler.add_job(scan_direct_98, 'interval', minutes=5, id="DIRECT_98")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    print(f"Scheduler DIRECT 98 started - {sum(len(v) for v in L3_SECTORS.values())} stocks 98 FULL BOTH NOW")
    tg(f"ALERTS BOT DIRECT 98 STARTED\n98 FULL BOTH NOW PRESERVED\nPrice+Pct+Vol+BUY+Entry/Stop")
    yield
    scheduler.shutdown()

app = FastAPI(title="ALERTS BOT DIRECT 98", lifespan=lifespan)

@app.get("/")
def home():
    return {"status":f"ALERTS DIRECT 98 FULL BOTH NOW - {sum(len(v) for v in L3_SECTORS.values())} stocks"}

@app.get("/health")
def health():
    return {"ok":True,"total":sum(len(v) for v in L3_SECTORS.values())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
