
"""
LINKED BOT UNIFIED - L1+L2+L3+L4 TRUE LINKED - 95 stocks - CBOE:SNDU + BOTH NOW
L3 = sector grouping (10 sectors)
L4 = sector-to-sector linking + gov triggers (all sectors linked from start)
- Loads L3_L4_UNIFIED_95_PERFECT.json if exists, else L3_sectors.json
- TradingView + L1(95) + L2(24) + L3(10 sectors) + L4(10 sectors linked)
"""
import os, json, requests, hashlib, time, pathlib, threading
from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
FINNHUB = os.getenv("FINNHUB_API_KEY", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "mysecret123")
PORT = int(os.getenv("PORT", "8000"))

BASE_DIR = pathlib.Path(__file__).parent
WATCH_DIR = BASE_DIR / "watchlists"
WATCH_DIR.mkdir(exist_ok=True)

print(f"LINKED BOT UNIFIED L3+L4 - TOKEN:{bool(TOKEN)} CHAT:{CHAT_ID} FINNHUB:{bool(FINNHUB)} SECRET:{WEBHOOK_SECRET} PORT:{PORT}")

# Default L1/L2 same as before (95)
DEFAULT_L1 = ['AAOI', 'ALB', 'AMD', 'AMZN', 'ANET', 'AQB', 'ARM', 'ARQQ', 'ASML', 'ASTS', 'AVGO', 'BBAI', 'BKSY', 'CCJ', 'CEVA', 'CIEN', 'CLS', 'COHR', 'CRWV', 'DELL', 'DRAM', 'DVLT', 'EBM', 'ENSC', 'EU', 'FN', 'GOOGL', 'HON', 'IBM', 'IONQ', 'IPWR', 'IREN', 'KLAC', 'LAC', 'LEU', 'LITE', 'LRCX', 'LUMN', 'LUNR', 'MCHP', 'MOD', 'MP', 'MRVL', 'MSFT', 'MSS', 'MU', 'NBIS', 'NDM', 'NNE', 'NOK', 'NOU', 'NOW', 'NTAP', 'NVDA', 'NXPI', 'OKLO', 'ON', 'ONDS', 'ORCL', 'PL', 'PLTR', 'POET', 'PSTG', 'PYPL', 'QBTS', 'QCOM', 'QUBT', 'RAM', 'RDW', 'RGTI', 'RIG', 'RKLB', 'SIMO', 'SMCI', 'SMR', 'SNDK', 'SNDU', 'SNPS', 'SOFI', 'SPCE', 'SQNS', 'STX', 'TE', 'TSLA', 'UBER', 'UEC', 'USAR', 'UUUU', 'VERI', 'VRT', 'VTIX', 'WDC', 'ZETA']  # 95 TVs -> 93 unique plain - BOTH NOW preserved - AI works on all 95

DEFAULT_L2 = {
    "NVDA": {"lifts": ["DRAM", "CRWV", "AAOI", "TSLA", "SIMO"], "reason": "NVDA drives memory/server/optics"},
    "MSFT": {"lifts": ["NOW", "ORCL", "CRWV", "IPWR"], "reason": "AI cloud mega"},
    "AMZN": {"lifts": ["NOW", "CRWV", "IPWR", "SOFI", "ONDS"], "reason": "AWS cloud + power chips"},
    "MU": {"lifts": ["DRAM", "RAM", "SNDU"], "reason": "DRAM leader"},
    "PLTR": {"lifts": ["BBAI", "NOW"], "reason": "Gov AI"},
    "LITE": {"lifts": ["POET", "AAOI", "ZETA"], "reason": "Optics leader 800G"},
    "SMCI": {"lifts": ["CRWV", "DELL"], "reason": "AI servers"},
    "VRT": {"lifts": ["CRWV", "IREN"], "reason": "AI infra"},
    "IONQ": {"lifts": ["QBTS"], "reason": "Quantum leader"},
    "OKLO": {"lifts": ["TE", "SMR"], "reason": "Nuclear for AI"},
}

def load_json(p, default):
    try:
        if p.exists():
            return json.loads(p.read_text())
    except: pass
    return default

# --- NEW: Load L3_L4 unified file that has everything linked from start ---
def load_l3_l4_unified():
    # Try unified first
    candidates = [
        WATCH_DIR / "L3_L4_UNIFIED_95_PERFECT.json",
        WATCH_DIR / "L3-L4-UNIFIED-95-PERFECT.json",
        WATCH_DIR / "L3_L4-UNIFIED-95-PERFECT.json",
        WATCH_DIR / "L3-L4_UNIFIED_95_PERFECT.json",
        WATCH_DIR / "L3_sectors.json",
        WATCH_DIR / "L3-sectors.json",
        BASE_DIR / "L3_L4_UNIFIED_95_PERFECT.json",
        BASE_DIR / "L3-L4-UNIFIED-95-PERFECT.json",
        BASE_DIR / "L3_sectors.json",
    ]
    for p in candidates:
        try:
            if p.exists():
                data = json.loads(p.read_text())
                # If unified format with 'sectors' key
                if isinstance(data, dict) and "sectors" in data:
                    print(f"L3_L4 UNIFIED loaded from {p.name}: {data['total_tickers']} tickers, {data['total_sectors']} sectors + L4 links")
                    return data
                # If old L3 format dict sector->list
                if isinstance(data, dict) and len(data) >= 5:
                    # check if values are lists
                    if all(isinstance(v, list) for v in data.values()):
                        total = sum(len(v) for v in data.values())
                        print(f"L3 loaded from {p.name}: {total} tickers, {len(data)} sectors (legacy, building L4 links)")
                        # Build minimal unified wrapper
                        return {
                            "version": "legacy_L3_to_L4",
                            "total_tickers": total,
                            "total_sectors": len(data),
                            "sectors": data,
                            "sector_links": {
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
                            },
                            "gov_triggers": {
                                "AI": ["AI_Power", "AI_Cooling", "Controller_Chip", "Chip_Mfg", "Quantum"],
                                "Nuclear": ["SMR_Nuclear", "Energy_Metals"],
                                "Space": ["Space_Drones", "Optical"],
                                "Storage": ["SSD_Storage", "Chip_Mfg"],
                            }
                        }
        except Exception as e:
            print(f"Failed load {p}: {e}")
    # Fallback empty
    return {"sectors": {}, "sector_links": {}, "gov_triggers": {}}

UNIFIED = load_l3_l4_unified()
L3_SECTORS = UNIFIED.get("sectors", {})
SECTOR_LINKS = UNIFIED.get("sector_links", {})
GOV_TRIGGERS = UNIFIED.get("gov_triggers", {})
LAYER_INFO = UNIFIED.get("layer_info", {})

# Build L1 watch from all sectors + default
all_tvs = []
for lst in L3_SECTORS.values():
    all_tvs.extend(lst)
# plain symbols
plain_from_l3 = [tv.split(":")[-1].replace(".V","").replace(".TO","") for tv in all_tvs]
L1_WATCH = sorted(list(set(DEFAULT_L1 + plain_from_l3 + [s.replace(".V","") for s in DEFAULT_L1])))

# L2 leaders
L2_LEADERS = load_json(WATCH_DIR / "L2_leaders.json", DEFAULT_L2)
# Try also base dir
if not L2_LEADERS or len(L2_LEADERS) < 5:
    L2_LEADERS = load_json(BASE_DIR / "L2_leaders.json", DEFAULT_L2)

print(f"L1 {len(L1_WATCH)} unique, L2 {len(L2_LEADERS)}, L3 {len(L3_SECTORS)} sectors, L4 links {len(SECTOR_LINKS)}")

# Helpers same as before
_last_sent = {}
_cooldown = {}
_seen_headlines = set()

def can_send(key, mins=30):
    now = datetime.utcnow()
    last = _cooldown.get(key)
    if last and now - last < timedelta(minutes=mins):
        return False
    _cooldown[key] = now
    return True

def is_dup(headline):
    h = hashlib.md5(headline.encode()).hexdigest()
    if h in _seen_headlines:
        return True
    _seen_headlines.add(h)
    if len(_seen_headlines) > 500:
        _seen_headlines.clear()
    return False

def tg(text, chat_id=None):
    cid = chat_id or CHAT_ID
    if not TOKEN or not cid:
        print(f"TG skip no token/chat: {text[:100]}")
        return
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": cid, "text": text[:4000], "disable_web_page_preview": True}, timeout=10)
        print(f"TG {r.status_code} OK: {text[:80]}")
    except Exception as e:
        print(f"TG Error {e}")

def get_hybrid(ticker):
    # simplified - Finnhub + mock
    if not FINNHUB:
        return []
    try:
        clean = ticker.split(":")[-1].replace(".V","").replace(".TO","")
        url = f"https://finnhub.io/api/v1/company-news?symbol={clean}&from={(datetime.utcnow()-timedelta(days=2)).strftime('%Y-%m-%d')}&to={datetime.utcnow().strftime('%Y-%m-%d')}&token={FINNHUB}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            news = []
            for n in data[:3]:
                if n.get("headline"):
                    news.append({"headline": n["headline"], "url": n.get("url",""), "source": "finnhub"})
            return news
    except Exception as e:
        print(f"Finnhub error {ticker} {e}")
    return []

def scan_L1():
    print(f"L1 Scan {len(L1_WATCH)} tickers")
    for ticker in L1_WATCH[:95]:
        if not can_send(f"L1_{ticker}", 60):
            continue
        news = get_hybrid(ticker)
        if news and not is_dup(news[0]["headline"]):
            tg(f"📈 L1 Ticker: {ticker}\n{news[0]['headline']}\nLink: {news[0].get('url','')}")

def scan_L2():
    print(f"L2 Scan {len(L2_LEADERS)} leaders")
    for leader, info in L2_LEADERS.items():
        if not can_send(f"L2_{leader}", 60):
            continue
        news = get_hybrid(leader)
        if news and any(k in news[0]["headline"].lower() for k in ["up", "gain", "surge", "beat", "gov", "contract"]):
            lifts = ", ".join(info["lifts"])
            tg(f"🚀 L2 Leader: {leader} -> lifts {lifts}\nReason: {info['reason']}\n{news[0]['headline']}\nLink: {news[0].get('url','')}")

def scan_L3():
    print(f"L3 Sectors Scan {len(L3_SECTORS)} - {sum(len(v) for v in L3_SECTORS.values())} total tickers")
    for sector_name, sector_data in L3_SECTORS.items():
        tickers = sector_data if isinstance(sector_data, list) else sector_data.get("tickers", [])
        if not tickers:
            continue
        # Pick 1-2 leaders from sector for news check
        sample = tickers[:2]
        for tv in sample:
            plain = tv.split(":")[-1].replace(".V","").replace(".TO","")
            if not can_send(f"L3_{sector_name}_{plain}", 120):
                continue
            news = get_hybrid(plain)
            if news and any(k in news[0]["headline"].lower() for k in ["government", "funding", "doe", "contract", "award", "investment"]):
                if not is_dup(news[0]["headline"]):
                    tg(f"🏭 L3 Sector: {sector_name}\nTicker: {tv} ({plain})\nGov News: {news[0]['headline']}\nLink: {news[0].get('url','')}\nSector size: {len(tickers)}")

def scan_L4():
    """L4 TRUE LINKED: sector-to-sector + gov triggers - all sectors linked from start"""
    print(f"L4 TRUE LINKED Scan {len(SECTOR_LINKS)} links, {len(GOV_TRIGGERS)} gov triggers")
    for gov_key, linked_sectors in GOV_TRIGGERS.items():
        if not can_send(f"L4_GOV_{gov_key}", 180):
            continue
        # Check one ticker from each linked sector for gov news
        triggered = []
        for sector in linked_sectors:
            sec_tickers = L3_SECTORS.get(sector, [])
            if not sec_tickers:
                continue
            for tv in sec_tickers[:1]:
                plain = tv.split(":")[-1].replace(".V","").replace(".TO","")
                news = get_hybrid(plain)
                if news and gov_key.lower() in news[0]["headline"].lower():
                    triggered.append((sector, tv, news[0]))
                    break
        if triggered:
            # If one sector triggers, all linked sectors are affected
            all_affected = set(linked_sectors)
            for sec, _, _ in triggered:
                all_affected.update(SECTOR_LINKS.get(sec, []))
            sectors_str = ", ".join(sorted(all_affected))
            first = triggered[0]
            if not is_dup(first[2]["headline"] + gov_key):
                tg(f"🔗 L4 TRUE LINKED - Gov: {gov_key.upper()}\nTriggered: {first[0]} ({first[1]})\nAll Linked Sectors: {sectors_str}\nNews: {first[2]['headline']}\nLink: {first[2].get('url','')}\nTotal affected sectors: {len(all_affected)}")

scheduler = BackgroundScheduler()
scheduler.add_job(scan_L1, 'interval', minutes=5, id="L1")
scheduler.add_job(scan_L2, 'interval', minutes=5, id="L2")
scheduler.add_job(scan_L3, 'interval', minutes=10, id="L3")
scheduler.add_job(scan_L4, 'interval', minutes=15, id="L4")

def handle_telegram():
    if not TOKEN:
        print("No TOKEN")
        return
    offset=0
    print("Telegram polling started")
    unique = len(set(L1_WATCH))
    tg(f"Linked Bot Started UNIFIED L3+L4 TRUE LINKED - L1 {len(L1_WATCH)} ({unique} unique) L2 {len(L2_LEADERS)} L3 {len(L3_SECTORS)} sectors {sum(len(v) for v in L3_SECTORS.values())} stocks L4 {len(SECTOR_LINKS)} links CBOE:SNDU BOTH NOW FIXED")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
            data = r.json()
            if not data.get("ok"):
                time.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"]+1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg: continue
                text = msg.get("text","").strip()
                if not text: continue
                lower=text.lower()
                if lower.startswith("/start"):
                    tg(f"Linked Bot UNIFIED L3+L4 - L1 {len(L1_WATCH)} L2 {len(L2_LEADERS)} L3 {len(L3_SECTORS)} L4 {len(SECTOR_LINKS)} links - /list L1 L2 L3 L4 - /scan ALL", msg["chat"]["id"])
                elif lower.startswith("/list"):
                    parts=text.split()
                    layer=parts[1].upper() if len(parts)>1 else "ALL"
                    if layer=="L3":
                        m=f"L3 {len(L3_SECTORS)}:\n"
                        for k,v in L3_SECTORS.items():
                            tickers = v if isinstance(v, list) else v.get("tickers", v)
                            m+=f"{k}: {len(tickers)} - {', '.join(tickers[:5])}...\n"
                        tg(m[:4000], msg["chat"]["id"])
                    elif layer=="L4":
                        m=f"L4 {len(SECTOR_LINKS)} TRUE LINKED:\n"
                        for k,v in SECTOR_LINKS.items():
                            m+=f"{k} -> {', '.join(v)}\n"
                        m+="\nGOV TRIGGERS:\n"
                        for k,v in GOV_TRIGGERS.items():
                            m+=f"{k}: {', '.join(v)}\n"
                        tg(m[:4000], msg["chat"]["id"])
                    else:
                        tg(f"ALL L1={len(L1_WATCH)} L2={len(L2_LEADERS)} L3={len(L3_SECTORS)} L4={len(SECTOR_LINKS)}", msg["chat"]["id"])
                elif lower.startswith("/scan"):
                    parts=text.split()
                    layer=parts[1].upper() if len(parts)>1 else "ALL"
                    tg(f"Scanning {layer}", msg["chat"]["id"])
                    if layer=="L1": scan_L1()
                    elif layer=="L2": scan_L2()
                    elif layer=="L3": scan_L3()
                    elif layer=="L4": scan_L4()
                    else:
                        scan_L1(); scan_L2(); scan_L3(); scan_L4()
                    tg(f"Scan {layer} Done", msg["chat"]["id"])
        except Exception as e:
            print(f"TG Error {e}")
            time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.start()
        print("Scheduler L1/L2/L3/L4 started")
    t = threading.Thread(target=handle_telegram, daemon=True)
    t.start()
    print("Telegram thread started")
    yield
    scheduler.shutdown()

app = FastAPI(title="Linked Bot Unified L3+L4 TRUE LINKED", lifespan=lifespan)

@app.get("/")
def home():
    return {
        "status": f"Linked UNIFIED L3+L4 TRUE LINKED - {sum(len(v) for v in L3_SECTORS.values())} stocks",
        "L1": len(L1_WATCH),
        "L2": len(L2_LEADERS),
        "L3": len(L3_SECTORS),
        "L4_links": len(SECTOR_LINKS),
        "total_tickers": sum(len(v) for v in L3_SECTORS.values()),
        "version": UNIFIED.get("version","unknown")
    }

@app.post("/webhook/tradingview")
async def webhook(req: Request):
    try:
        data = await req.json()
    except:
        body = await req.body()
        try:
            data = json.loads(body.decode())
        except:
            data = {}
    if data.get("secret") != WEBHOOK_SECRET:
        return {"unauthorized": 1}
    ticker = data.get("ticker","").split(":")[-1].strip().upper()
    if not ticker:
        ticker = data.get("symbol","").split(":")[-1].strip().upper()
    price = data.get("price","") or data.get("close","")
    action = data.get("action","signal")
    if not ticker:
        return {"error": "no ticker"}
    if not can_send(f"TV_{ticker}", 2):
        return {"cooldown": 1}
    news = get_hybrid(ticker)
    layer_info = "L1"
    if ticker in L2_LEADERS:
        layer_info = f"L2 Leader lifts {', '.join(L2_LEADERS[ticker]['lifts'])}"
    else:
        for sec, sec_data in L3_SECTORS.items():
            sec_tickers = sec_data if isinstance(sec_data, list) else sec_data.get("tickers", sec_data)
            sec_plain = [t.split(":")[-1] for t in sec_tickers]
            if ticker in sec_plain or ticker in sec_tickers:
                linked = SECTOR_LINKS.get(sec, [])
                layer_info = f"L3 {sec} | L4 links -> {', '.join(linked[:3])}"
                break
    if news and not is_dup(news[0]["headline"]):
        tg(f"TV + News L3+L4 LINKED\nTicker: {ticker} - {action} @ {price}\nLayer: {layer_info}\n{news[0]['headline']}\nLink: {news[0].get('url','')}")
    else:
        tg(f"TV Signal No Fresh News L3+L4\nTicker: {ticker} - {action} @ {price}\nLayer: {layer_info}")
    return {"ok": True, "ticker": ticker}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
