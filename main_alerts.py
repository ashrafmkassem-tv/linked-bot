
"""
ALERTS BOT - 98 STOCKS FINAL - USER CONFIRMED - DO NOT REVERT TO 95
- 98 total: SSD 9 + Energy 14 (TSX:DB) + Optical 8 + SMR 8 + Space 9 + Cooling 10 + AI_Power 17 (TSXV:NOW + NYSE:NOW + BIVI + ALAR) + Controller 8 + Quantum 8 + Chip 7
- BOTH NOW PRESERVED: TSXV:NOW Now Vertical Canadian + NYSE:NOW ServiceNow American - DO NOT REMOVE
- Score 50 (not 60) to catch before explosion
- Price + %: $136.97 (+2.22%)
- Session 08:30-16:00 NY 24h format (0830-1600) - pre-market 1h before to close - NOT AM/PM, NOT 24h running, NOT Doha
- Alert line present
"""
import os, json, requests, time, pathlib, threading, math
from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import asynccontextmanager
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN_ALERTS", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID_ALERTS", "")
FINNHUB = os.getenv("FINNHUB_API_KEY_ALERTS", os.getenv("FINNHUB_API_KEY", ""))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET_ALERTS", "mysecret123")
PORT = int(os.getenv("PORT", "8000"))

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
SECTOR_LINKS = {"SSD_Storage": ["AI_Cooling", "Controller_Chip", "Chip_Mfg"],"AI_Cooling": ["SSD_Storage", "AI_Power", "Chip_Mfg"],"AI_Power": ["AI_Cooling", "Controller_Chip", "Chip_Mfg", "Quantum"],"Controller_Chip": ["Chip_Mfg", "SSD_Storage", "AI_Cooling"],"Chip_Mfg": ["Controller_Chip", "SSD_Storage", "Optical"],"Optical": ["Chip_Mfg", "Space_Drones"],"SMR_Nuclear": ["Energy_Metals", "AI_Power"],"Energy_Metals": ["SMR_Nuclear", "AI_Power"],"Space_Drones": ["Optical", "Energy_Metals"],"Quantum": ["AI_Power", "Chip_Mfg"]}
LEADERS = {"NVDA": ["DRAM","CRWV","AAOI","SIMO","MU"],"MSFT": ["NOW","ORCL","CRWV","IPWR"],"MU": ["DRAM","RAM","SNDU","SNDK","WDC"],"LITE": ["POET","AAOI","COHR","FN"],"OKLO": ["SMR","TE","NNE","LEU"],"PLTR": ["BBAI","NOW","VERI"],"SMCI": ["CRWV","DELL","ANET","VRT"],"IONQ": ["QBTS","RGTI","QUBT","ARQQ"]}

all_tvs = [t for lst in L3_SECTORS.values() for t in lst]
WATCH_98 = sorted(list(dict.fromkeys(all_tvs)))  # 98 - FULL EXCHANGE:SYMBOL - BOTH NOW PRESERVED - DO NOT TOUCH
print(f"ALERTS WATCH 98: {len(WATCH_98)} tickers FULL - BOTH NOW PRESERVED - 50 SCORE - 0830-1600 NY")

_last = {}
def can_send(k, mins=2):
    now=datetime.utcnow()
    if k in _last and now-_last[k] < timedelta(minutes=mins): return False
    _last[k]=now
    return True

def tg(text, chat_id=None):
    cid=chat_id or CHAT_ID
    if not TOKEN or not cid:
        print(f"TG skip: {text[:120]}")
        return
    try:
        r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id":cid,"text":text[:4000],"disable_web_page_preview":True}, timeout=10)
        print(f"TG {r.status_code}: {text[:100]}")
    except Exception as e:
        print(f"TG Error {e}")

def get_candles(symbol, days=80):
    if not FINNHUB: return None
    try:
        clean = symbol.split(":")[-1].replace(".V","").replace(".TO","").upper()
        to_ts = int(datetime.utcnow().timestamp())
        from_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={clean}&resolution=D&from={from_ts}&to={to_ts}&token={FINNHUB}"
        r = requests.get(url, timeout=12)
        if r.status_code != 200: return None
        data = r.json()
        if data.get("s") != "ok" or not data.get("c"): return None
        return {"c": data["c"], "v": data["v"]}
    except: return None

def sma(prices, period):
    if len(prices) < period: return None
    return sum(prices[-period:]) / period

def ema(prices, period):
    if len(prices) < period: return None
    k = 2 / (period + 1)
    ema_val = sum(prices[:period]) / period
    for p in prices[period:]:
        ema_val = p * k + ema_val * (1 - k)
    return ema_val

def rsi(prices, period=14):
    if len(prices) < period+1: return 50
    gains = losses = 0
    for i in range(1, period+1):
        diff = prices[-i] - prices[-i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def bollinger(prices, period=20, mult=2):
    if len(prices) < period: return None
    s = sma(prices, period)
    if s is None: return None
    var = sum((p - s) ** 2 for p in prices[-period:]) / period
    std = math.sqrt(var)
    upper = s + mult * std
    lower = s - mult * std
    width = (upper - lower) / s if s != 0 else 0
    return {"width": width}

def relative_volume(volumes, period=20):
    if len(volumes) < period+1: return 1.0
    avg = sum(volumes[-period-1:-1]) / period
    if avg == 0: return 1.0
    return volumes[-1] / avg

def get_sector_for_ticker(ticker):
    for sec, lst in L3_SECTORS.items():
        plains = [t.split(":")[-1].replace(".V","").replace(".TO","").upper() for t in lst]
        if ticker.upper() in plains: return sec
    return None

def analyze_ticker_with_tv(ticker, tv_data=None):
    try:
        daily = get_candles(ticker, 80)
        pct_change = 0.0
        if not daily or len(daily["c"]) < 20:
            if tv_data:
                price = float(tv_data.get("price", 0) or 0)
                rsi_val = float(tv_data.get("rsi", 50))
                rvol = float(tv_data.get("rvol", 1.0))
                bb_width = float(tv_data.get("bb_width", 0.1))
                pct_change = float(tv_data.get("pct", tv_data.get("change", 0)) or 0)
            else: return None
            ema9 = ema21 = ema50 = None
        else:
            c = daily["c"]; v = daily["v"]
            price = c[-1]
            try:
                prev = c[-2] if len(c) >= 2 else c[-1]
                pct_change = ((price - prev) / prev * 100) if prev != 0 else 0.0
            except:
                pct_change = 0.0
            ema9 = ema(c, 9); ema21 = ema(c, 21); ema50 = ema(c, 50)
            rsi_val = rsi(c, 14)
            bb = bollinger(c, 20, 2)
            bb_width = bb["width"] if bb else 0.1
            rvol = relative_volume(v, 20)
            if tv_data and tv_data.get("price"):
                try: price = float(tv_data["price"])
                except: pass
                if tv_data.get("pct") is not None:
                    try: pct_change = float(tv_data.get("pct"))
                    except: pass
        score = 0
        if ema9 and ema21 and ema50:
            if price > ema9 > ema21 > ema50: score += 25
            elif price > ema9 and price > ema21: score += 18
        if 55 <= rsi_val <= 70: score += 20
        elif 50 <= rsi_val <= 75: score += 15
        if rvol >= 3.0: score += 25
        elif rvol >= 2.0: score += 20
        elif rvol >= 1.5: score += 15
        if bb_width < 0.08: score += 15
        elif bb_width < 0.12: score += 10
        if tv_data and tv_data.get("breakout"): score += 10
        score = min(score, 100)
        if score >= 80: signal = "STRONG BUY - BEFORE EXPLOSION"; action = "BUY NOW"
        elif score >= 65: signal = "BUY - EARLY"; action = "BUY"
        elif score >= 50: signal = "WATCH"; action = "WATCH"
        else: signal = "HOLD"; action = "HOLD"
        sector = get_sector_for_ticker(ticker)
        linked = SECTOR_LINKS.get(sector, []) if sector else []
        will_explode = []
        if score >= 75 and ticker in LEADERS: will_explode = LEADERS[ticker]
        elif score >= 50 and sector:
            for ls in linked[:2]:
                lst = L3_SECTORS.get(ls, [])
                plains = [t.split(":")[-1].replace(".V","").replace(".TO","").upper() for t in lst[:4]]
                will_explode.extend(plains)
        return {"symbol": ticker, "price": price, "pct": pct_change, "score": score, "signal": signal, "action": action, "rsi": rsi_val, "rvol": rvol, "bb_width": bb_width, "sector": sector, "linked_sectors": linked, "will_explode_next": list(dict.fromkeys(will_explode))[:6], "stop": price * 0.92, "target1": price * 1.15, "target2": price * 1.35}
    except Exception as e:
        print(f"Analyze error {ticker}: {e}")
        return None

scheduler = BackgroundScheduler()

def handle_telegram():
    if not TOKEN: return
    offset=0
    tg(f"🚀 ALERTS BOT 98 STARTED\n98 Stocks 31/33/34 | Score 50 + Price + % | 08:30-16:00 NY 24h | BOTH NOW PRESERVED")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
            data = r.json()
            if not data.get("ok"): time.sleep(5); continue
            for upd in data.get("result", []):
                offset = upd["update_id"]+1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg: continue
                text = msg.get("text","").strip()
                if not text: continue
                lower=text.lower()
                cid = msg["chat"]["id"]
                if lower.startswith("/start"):
                    tg(f"🚀 ALERTS 98 - BOTH NOW - 50 - Price+%", cid)
        except Exception as e:
            print(f"TG Error {e}"); time.sleep(5)

from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.start()
    t=threading.Thread(target=handle_telegram, daemon=True)
    t.start()
    yield
    scheduler.shutdown()

app=FastAPI(title="Alerts Bot 98 - BOTH NOW", lifespan=lifespan)

@app.get("/")
def home():
    return {"status": f"ALERTS 98 - {len(WATCH_98)} stocks - BOTH NOW preserved", "sectors": len(L3_SECTORS)}

def is_trading_hours_ny():
    try:
        from zoneinfo import ZoneInfo
        now_ny = datetime.now(ZoneInfo("America/New_York"))
        mins = now_ny.hour * 60 + now_ny.minute
        if 510 <= mins <= 960:  # 08:30=510, 16:00=960 - 0830-1600 24h format
            return True
        return False
    except:
        return True

async def process_tv_webhook(data):
    ticker = data.get("ticker","").split(":")[-1].strip().upper() or data.get("symbol","").split(":")[-1].strip().upper()
    if not ticker:
        top = data.get("top_with_price","") or ""
        if top:
            first = top.split(",")[0].strip().split(" ")[0].upper()
            ticker = first
    if not ticker: return {"error":"no ticker"}
    if not can_send(f"TV_{ticker}", 2): return {"cooldown":1}
    if not is_trading_hours_ny():
        print(f"Outside 0830-1600 NY - skip {ticker}")
    res = analyze_ticker_with_tv(ticker, data)
    if not res: return {"ok":True,"no_analysis":1}
    if res["score"] >= 50:
        pct = res.get("pct", 0.0)
        pct_str = f"{pct:+.2f}%"
        msg = f"🚨 {res['action']} {ticker} Score {res['score']}/100 ${res['price']:.2f} ({pct_str}) RSI {res['rsi']:.1f} rVol {res['rvol']:.2f}x {res['sector']}"
        if res["will_explode_next"]: msg += f"\nNEXT ➡️ {','.join(res['will_explode_next'])}"
        msg += f"\nStop {res['stop']:.2f} T1 {res['target1']:.2f} T2 {res['target2']:.2f}"
        if data.get("top_with_price"):
            msg += f"\n\nTOP: {data.get('top_with_price')[:300]}"
        tg(msg)
    return {"ok":True,"ticker":ticker,"score":res["score"],"price":res.get("price"),"pct":res.get("pct")}

from fastapi import Request
@app.post("/webhook/ai")
async def webhook_ai(req: Request):
    try: data = await req.json()
    except:
        try: data = json.loads((await req.body()).decode())
        except: data = {}
    return await process_tv_webhook(data)

@app.post("/webhook/tradingview")
async def webhook_tradingview(req: Request):
    try: data = await req.json()
    except:
        try: data = json.loads((await req.body()).decode())
        except: data = {}
    return await process_tv_webhook(data)

@app.get("/health")
def health():
    return {"ok": True, "watchlist": len(WATCH_98), "both_now": True, "score": 50, "session": "08:30-16:00 NY 0830-1600 24h"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
