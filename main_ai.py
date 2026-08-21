"""
AI TRADINGVIEW ANALYZER - 95 STOCKS PROFESSIONAL CANDLE ANALYSIS
NO WEBHOOK NEEDED - SCANS DIRECTLY FROM FINNHUB CANDLES
Predicts explosion BEFORE it happens - BUY/SELL with professional analysis
- Reads L3_sectors.json (10 sectors, 95 tickers)
- Professional TA: RSI, EMA, SMA, BB, ATR, MACD, Volume, VWAP
- Explosion Score 0-100, Sector Linking, Before-Explosion Prediction
"""

import os, json, requests, time, pathlib, threading, math
from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
FINNHUB = os.getenv("FINNHUB_API_KEY", "")
PORT = int(os.getenv("PORT", "8000"))

BASE_DIR = pathlib.Path(__file__).parent
WATCH_DIR = BASE_DIR / "watchlists"
WATCH_DIR.mkdir(exist_ok=True)

print(f"AI ANALYZER 95 - TOKEN:{bool(TOKEN)} CHAT:{CHAT_ID} FINNHUB:{bool(FINNHUB)} PORT:{PORT}")

def load_sectors():
    for p in [BASE_DIR/"L3_sectors.json", BASE_DIR/"watchlists"/"L3_sectors.json", BASE_DIR/"watchlists"/"L3_L4_UNIFIED_95_PERFECT.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict) and "sectors" in data:
                    return data["sectors"]
                if isinstance(data, dict) and all(isinstance(v,list) for v in data.values()):
                    return data
            except: pass
    return {}

L3_SECTORS = load_sectors()
SECTOR_LINKS = {
    "SSD_Storage": ["AI_Cooling", "Controller_Chip", "Chip_Mfg"],
    "AI_Cooling": ["SSD_Storage", "AI_Power", "Chip_Mfg"],
    "AI_Power": ["AI_Cooling", "Controller_Chip", "Chip_Mfg", "Quantum"],
    "Controller_Chip": ["Chip_Mfg", "SSD_Storage", "AI_Cooling"],
    "Chip_Mfg": ["Controller_Chip", "SSD_Storage", "Optical"],
    "Optical": ["Chip_Mfg", "Space_Drones"],
    "SMR_Nuclear": ["Energy_Metals", "AI_Power"],
    "Energy_Metals": ["SMR_Nuclear", "AI_Power"],
    "Space_Drones": ["Optical", "Energy_Metals"],
    "Quantum": ["AI_Power", "Chip_Mfg"]
}
LEADERS = {
    "NVDA": ["DRAM","CRWV","AAOI","SIMO","MU"],
    "MSFT": ["NOW","ORCL","CRWV","IPWR"],
    "MU": ["DRAM","RAM","SNDU","SNDK","WDC"],
    "LITE": ["POET","AAOI","COHR","FN"],
    "OKLO": ["SMR","TE","NNE","LEU"],
    "PLTR": ["BBAI","NOW","VERI"],
    "SMCI": ["CRWV","DELL","ANET","VRT"],
    "IONQ": ["QBTS","RGTI","QUBT","ARQQ"]
}

all_tvs = [t for lst in L3_SECTORS.values() for t in lst]
plain_tickers = []
for tv in all_tvs:
    clean = tv.split(":")[-1].replace(".V","").replace(".TO","").strip().upper()
    if clean and clean not in plain_tickers:
        plain_tickers.append(clean)
WATCH_95 = sorted(list(set(plain_tickers)))[:95]
print(f"AI WATCH 95: {len(WATCH_95)} tickers from {len(L3_SECTORS)} sectors")

_last = {}
def can_send(k, mins=30):
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

def get_candles(symbol, resolution="D", days=60):
    if not FINNHUB: return None
    try:
        clean = symbol.split(":")[-1].replace(".V","").replace(".TO","").upper()
        to_ts = int(datetime.utcnow().timestamp())
        from_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={clean}&resolution={resolution}&from={from_ts}&to={to_ts}&token={FINNHUB}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return None
        data = r.json()
        if data.get("s") != "ok" or not data.get("c"): return None
        return {"c": data["c"], "o": data["o"], "h": data["h"], "l": data["l"], "v": data["v"], "t": data["t"]}
    except Exception as e:
        print(f"Candle error {symbol}: {e}")
        return None

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
    gains = 0; losses = 0
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
    variance = sum((p - s) ** 2 for p in prices[-period:]) / period
    std = math.sqrt(variance)
    upper = s + mult * std
    lower = s - mult * std
    width = (upper - lower) / s if s != 0 else 0
    return {"sma": s, "upper": upper, "lower": lower, "width": width, "price": prices[-1]}

def atr(high, low, close, period=14):
    if len(close) < period+1: return None
    trs = []
    for i in range(1, len(close)):
        tr = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
        trs.append(tr)
    if len(trs) < period: return None
    return sum(trs[-period:]) / period

def relative_volume(volumes, period=20):
    if len(volumes) < period+1: return 1.0
    avg = sum(volumes[-period-1:-1]) / period
    if avg == 0: return 1.0
    return volumes[-1] / avg

def macd(prices):
    if len(prices) < 26: return {"bull": False, "value": 0, "rising": False}
    ema12 = ema(prices, 12); ema26 = ema(prices, 26)
    if ema12 is None or ema26 is None: return {"bull": False, "value": 0, "rising": False}
    macd_line = ema12 - ema26
    prev_ema12 = ema(prices[:-1], 12) if len(prices) > 26 else ema12
    prev_ema26 = ema(prices[:-1], 26) if len(prices) > 26 else ema26
    if prev_ema12 is None or prev_ema26 is None:
        return {"bull": macd_line > 0, "value": macd_line, "rising": False}
    prev_macd = prev_ema12 - prev_ema26
    return {"bull": macd_line > 0 and macd_line > prev_macd, "value": macd_line, "rising": macd_line > prev_macd}

def detect_consolidation(high, low, close, period=5):
    if len(close) < period: return False
    recent_high = max(high[-period:]); recent_low = min(low[-period:])
    range_pct = (recent_high - recent_low) / close[-1] if close[-1] != 0 else 1
    return range_pct < 0.08

def analyze_ticker(symbol):
    try:
        daily = get_candles(symbol, "D", 80)
        if not daily or len(daily["c"]) < 30: return None
        c = daily["c"]; o = daily["o"]; h = daily["h"]; l = daily["l"]; v = daily["v"]
        price = c[-1]
        ema9 = ema(c, 9); ema21 = ema(c, 21); ema50 = ema(c, 50); ema200 = ema(c, 200) if len(c) >=200 else None
        rsi_val = rsi(c, 14); bb = bollinger(c, 20, 2); atr_val = atr(h, l, c, 14); rvol = relative_volume(v, 20)
        macd_data = macd(c); consolid = detect_consolidation(h, l, c, 5)
        score = 0; reasons = []
        trend_score = 0
        if ema9 and ema21 and ema50:
            if price > ema9 > ema21 > ema50:
                trend_score = 25; reasons.append("🔥 Strong Uptrend EMA9>21>50")
            elif price > ema9 and price > ema21:
                trend_score = 18; reasons.append("📈 Uptrend above EMA9/21")
            elif price > ema21:
                trend_score = 10; reasons.append("Above EMA21")
            elif ema200 and price > ema200:
                trend_score = 5
        score += trend_score
        mom_score = 0
        if 55 <= rsi_val <= 70 and macd_data["bull"]:
            mom_score = 20; reasons.append(f"💪 RSI {rsi_val:.1f} Bull Momentum + MACD")
        elif 50 <= rsi_val <= 75:
            mom_score = 15; reasons.append(f"RSI {rsi_val:.1f} Healthy")
        elif rsi_val > 70:
            mom_score = 8; reasons.append(f"⚠️ RSI {rsi_val:.1f} Overbought but strong")
        elif rsi_val >= 45:
            mom_score = 5
        score += mom_score
        vol_score = 0
        if rvol >= 3.0:
            vol_score = 25; reasons.append(f"🚀 EXPLOSION VOL rVol {rvol:.2f}x")
        elif rvol >= 2.0:
            vol_score = 20; reasons.append(f"📊 High Volume rVol {rvol:.2f}x")
        elif rvol >= 1.5:
            vol_score = 15; reasons.append(f"Volume Building {rvol:.2f}x")
        elif rvol >= 1.2:
            vol_score = 10
        elif len(v) >=3 and v[-1] > v[-2] > v[-3]:
            vol_score = 8; reasons.append("Volume Rising 3 days")
        score += vol_score
        squeeze_score = 0
        if bb:
            if bb["width"] < 0.08 and price >= bb["sma"]:
                squeeze_score = 15; reasons.append(f"💥 BB Squeeze {bb['width']:.3f} - About to EXPLODE")
            elif bb["width"] < 0.12:
                squeeze_score = 10; reasons.append(f"BB Squeeze Tight {bb['width']:.3f}")
            if price > bb["upper"]:
                reasons.append("Above BB Upper - Breakout"); squeeze_score += 5
        if consolid:
            squeeze_score = max(squeeze_score, 12); reasons.append("📦 5-Day Consolidation - Coiling")
        score += min(squeeze_score, 15)
        pat_score = 0
        if len(c) >=5 and c[-1] > c[-2] > c[-3]:
            pat_score += 5; reasons.append("Higher Highs Pattern")
        if len(h) >=10:
            recent_high = max(h[-10:-1])
            if price > recent_high:
                pat_score += 10; reasons.append(f"🔓 Breakout Above {recent_high:.2f}")
        score += min(pat_score, 15)
        score = min(score, 100)
        if score >= 75:
            signal = "STRONG BUY - BEFORE EXPLOSION"; action = "BUY NOW"
        elif score >= 60:
            signal = "BUY - EARLY ENTRY"; action = "BUY"
        elif score >= 50:
            signal = "WATCHLIST - BUILDING"; action = "WATCH"
        elif rsi_val > 80 and rvol > 2.5:
            signal = "SELL - CLIMAX"; action = "SELL"
        else:
            signal = "HOLD"; action = "HOLD"
        stop = price * 0.92 if action in ["BUY","BUY NOW"] else None
        target1 = price * 1.15; target2 = price * 1.35
        return {"symbol": symbol, "price": price, "score": score, "signal": signal, "action": action, "rsi": rsi_val, "rvol": rvol, "ema9": ema9, "ema21": ema21, "bb_width": bb["width"] if bb else 0, "reasons": reasons, "stop": stop, "target1": target1, "target2": target2, "atr": atr_val}
    except Exception as e:
        print(f"Analyze error {symbol}: {e}")
        return None

def get_sector_for_ticker(ticker):
    for sec, lst in L3_SECTORS.items():
        plains = [t.split(":")[-1].replace(".V","").replace(".TO","").upper() for t in lst]
        if ticker.upper() in plains: return sec
    return None

def boost_scores_with_sector_linking(results):
    leaders_high = {r["symbol"]: r for r in results if r["score"] >= 70}
    boosted = []
    for r in results:
        base_score = r["score"]; boost = 0; boost_reasons = []
        sector = get_sector_for_ticker(r["symbol"])
        if sector:
            linked_sectors = SECTOR_LINKS.get(sector, [])
            for leader, lifts in LEADERS.items():
                if leader in leaders_high and r["symbol"] in lifts:
                    leader_score = leaders_high[leader]["score"]
                    if leader_score >= 75:
                        boost += 15; boost_reasons.append(f"Leader {leader} Exploding {leader_score} -> Boost +15")
                leader_sec = get_sector_for_ticker(leader)
                if leader_sec and leader_sec in linked_sectors and leader in leaders_high:
                    if leaders_high[leader]["score"] >=70 and r["score"] >=45:
                        boost += 10; boost_reasons.append(f"Sector Link {leader_sec}->{sector} +10")
        r["boost"] = boost; r["final_score"] = min(base_score + boost, 100); r["boost_reasons"] = boost_reasons
        if r["final_score"] >= 75 and r["action"] != "BUY NOW":
            r["signal"] = "STRONG BUY - SECTOR LINK BEFORE EXPLOSION"; r["action"] = "BUY NOW"
        elif r["final_score"] >= 60 and r["final_score"] <75 and r["action"] == "HOLD":
            r["signal"] = "BUY - SECTOR LINK EARLY"; r["action"] = "BUY"
        boosted.append(r)
    return boosted

def scan_ai_95():
    print(f"[{datetime.now()}] AI SCAN 95 START - Professional Candle Analysis")
    results = []
    for i, ticker in enumerate(WATCH_95):
        if i % 15 == 0: print(f"  Scanning {i+1}/{len(WATCH_95)} - {ticker}")
        res = analyze_ticker(ticker)
        if res: results.append(res)
        if (i+1) % 10 == 0: time.sleep(1.2)
    if not results:
        print("No results"); return
    results = boost_scores_with_sector_linking(results)
    results.sort(key=lambda x: x["final_score"], reverse=True)
    strong_buys = [r for r in results if r["final_score"] >= 70]
    buys = [r for r in results if 60 <= r["final_score"] < 70]
    watch = [r for r in results if 50 <= r["final_score"] < 60]
    if strong_buys:
        msg = f"🚀 AI BEFORE EXPLOSION - {len(strong_buys)} STOCKS\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC\nScanned: {len(results)}/95\n\n"
        for r in strong_buys[:7]:
            msg += f"🔥 {r['symbol']} ${r['price']:.2f} Score {r['final_score']}/100\nSignal: {r['signal']}\nRSI {r['rsi']:.1f} | rVol {r['rvol']:.2f}x | BB {r['bb_width']:.3f}\n"
            for reason in r["reasons"][:3]: msg += f"• {reason}\n"
            if r.get("boost_reasons"):
                for br in r["boost_reasons"]: msg += f"• {br}\n"
            if r["action"] in ["BUY","BUY NOW"]:
                msg += f"Entry: NOW ${r['price']:.2f} | Stop {r['stop']:.2f} | T1 {r['target1']:.2f} T2 {r['target2']:.2f}\n"
            msg += "\n"
        if can_send("STRONG_BUY_ALERT", 15): tg(msg)
    if buys and can_send("BUY_ALERT", 30):
        msg2 = f"📈 AI EARLY ENTRY - {len(buys)} stocks Score 60-69\n\n"
        for r in buys[:5]: msg2 += f"{r['symbol']} ${r['price']:.2f} Score {r['final_score']} RSI {r['rsi']:.0f} rVol {r['rvol']:.1f}x\n"
        tg(msg2)
    if can_send("DAILY_TOP10", 180):
        msg3 = f"🏆 AI TOP 10 EXPLOSION CANDIDATES\n{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC\n\n"
        for i, r in enumerate(results[:10], 1):
            sector = get_sector_for_ticker(r['symbol']) or "Unknown"
            msg3 += f"{i}. {r['symbol']} ({sector}) Score {r['final_score']} ${r['price']:.2f} {r['action']}\n"
        tg(msg3)
    print(f"AI SCAN DONE - Strong {len(strong_buys)} Buy {len(buys)} Watch {len(watch)}")
    return results

scheduler = BackgroundScheduler()
scheduler.add_job(scan_ai_95, 'interval', minutes=10, id="AI_95")

def handle_telegram():
    if not TOKEN:
        print("No TOKEN"); return
    offset=0
    print("Telegram AI polling started")
    tg(f"🤖 AI CANDLE ANALYZER STARTED\n95 Stocks | Professional TA | Before Explosion Prediction\nL3 {len(L3_SECTORS)} sectors | L4 {len(SECTOR_LINKS)} links\nBUY/SELL Signals with Entry/Stop/Target\nNo Webhook Needed - Direct Candle Analysis")
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
                if lower.startswith("/start"):
                    tg(f"🤖 AI 95 STOCKS\nCommands:\n/scan - Scan now\n/top10 - Top 10 candidates\n/analyze <ticker> - Analyze one\nL3 {len(L3_SECTORS)} sectors {len(WATCH_95)} stocks", msg["chat"]["id"])
                elif lower.startswith("/scan"):
                    tg("🔍 AI Scanning 95 stocks - Professional Candle Analysis - 2 mins...", msg["chat"]["id"])
                    results = scan_ai_95()
                    if results:
                        top = sorted(results, key=lambda x: x["final_score"], reverse=True)[:5]
                        m = "Scan Done - Top:\n"
                        for r in top: m+=f"{r['symbol']} Score {r['final_score']} {r['action']}\n"
                        tg(m, msg["chat"]["id"])
                    else:
                        tg("Scan done - no data (Finnhub limit?)", msg["chat"]["id"])
                elif lower.startswith("/analyze"):
                    parts=text.split()
                    if len(parts)>=2:
                        ticker=parts[1].upper()
                        tg(f"Analyzing {ticker}...", msg["chat"]["id"])
                        res=analyze_ticker(ticker)
                        if res:
                            m=f"📊 {res['symbol']} ${res['price']:.2f} Score {res.get('final_score', res['score'])}/100\n{res['signal']}\nRSI {res['rsi']:.1f} rVol {res['rvol']:.2f}x\n"
                            for reason in res["reasons"][:4]: m+=f"• {reason}\n"
                            if res["action"] in ["BUY","BUY NOW"]: m+=f"Entry {res['price']:.2f} Stop {res['stop']:.2f} T1 {res['target1']:.2f}\n"
                            tg(m, msg["chat"]["id"])
                        else:
                            tg(f"Failed to analyze {ticker}", msg["chat"]["id"])
                elif lower.startswith("/top10"):
                    tg("Getting Top 10...", msg["chat"]["id"])
                    results=[]
                    for t in WATCH_95[:20]:
                        res=analyze_ticker(t)
                        if res: results.append(res)
                        time.sleep(0.5)
                    results.sort(key=lambda x: x["score"], reverse=True)
                    m="🏆 TOP 10 Quick Scan:\n"
                    for i,r in enumerate(results[:10],1):
                        m+=f"{i}. {r['symbol']} Score {r['score']} {r['action']} ${r['price']:.2f}\n"
                    tg(m, msg["chat"]["id"])
        except Exception as e:
            print(f"TG Error {e}"); time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.start()
        print("Scheduler AI 95 started every 10 mins")
    t = threading.Thread(target=handle_telegram, daemon=True)
    t.start()
    print("Telegram AI thread started")
    yield
    scheduler.shutdown()

app = FastAPI(title="AI Candle Analyzer 95", lifespan=lifespan)

@app.get("/")
def home():
    return {"status": f"AI Analyzer 95 - {len(WATCH_95)} stocks - Professional TA", "sectors": len(L3_SECTORS), "watchlist": len(WATCH_95), "mode": "Before Explosion Prediction - BUY/SELL", "version": "AI v1.0 - No Webhook Needed"}

@app.get("/scan")
def trigger_scan():
    threading.Thread(target=scan_ai_95, daemon=True).start()
    return {"status": "AI Scan started", "tickers": len(WATCH_95)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
