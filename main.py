"""
FINAL LINKED BOT - UNIFIED MASTER 93 stocks - FIXED v3 - Railway Ready
- TradingView + L1(93 unified) + L2(24 leaders) + L3(10 sectors 93 stocks)
- Fixed: QSTS->QBTS, NOW + NOW.V preserved, Railway PORT support
- Run: python main.py
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

print(f"LINKED BOT UNIFIED - TOKEN:{bool(TOKEN)} CHAT:{CHAT_ID} FINNHUB:{bool(FINNHUB)} SECRET:{WEBHOOK_SECRET} PORT:{PORT}")

# Unified Master - single source of truth for all layers
DEFAULT_L1 = ['AAOI', 'ALB', 'AMAT', 'AMD', 'AMZN', 'AQB', 'AQN', 'ASML', 'ASTS', 'AVAV', 'AVGO', 'BB', 'BBAI', 'BIP', 'BITF', 'CCJ', 'CCJ.TO', 'CEVA', 'CIEN', 'COHR', 'CRWV', 'DELL', 'DNN', 'DRAM', 'DVLT', 'EBM', 'EME', 'ENSC', 'ETN', 'EU', 'FCX', 'FN', 'FTS', 'HIVE', 'HIVE.TO', 'HUBB', 'HUT', 'IONQ', 'IPWR', 'IREN', 'LAC', 'LEU', 'LITE', 'LUNR', 'MCHP', 'MDA.TO', 'MRVL', 'MSFT', 'MSS', 'MU', 'NBIS', 'NDM', 'NNE', 'NOK', 'NOL', 'NOU', 'NOV', 'NOW', 'NOW.V', 'NPI.TO', 'NVDA', 'OKLO', 'ONDS', 'ORCL', 'PLTR', 'POET', 'PYPL', 'QBTS', 'QUBT', 'RAM', 'RCAT', 'RGTI', 'RIG', 'SIMO', 'SMCI', 'SMR', 'SNDU', 'SOFI', 'SPCE', 'SQNS', 'STX', 'SWKS', 'TE', 'TSLA', 'TSM', 'UBER', 'USAR', 'UUUU', 'VERI', 'VRT', 'VTIX', 'WDC', 'ZETA']

DEFAULT_L2 = {
    "IONQ": {
        "lifts": [
            "QBTS"
        ],
        "reason": "Quantum leader - DOE lifts QBTS"
    },
    "RGTI": {
        "lifts": [
            "QBTS"
        ],
        "reason": "Quantum"
    },
    "QUBT": {
        "lifts": [
            "QBTS"
        ],
        "reason": "Quantum"
    },
    "MSFT": {
        "lifts": [
            "NOW",
            "NOW.V",
            "ORCL",
            "CRWV",
            "IPWR"
        ],
        "reason": "AI cloud mega - lifts NOW, NOW.V, ORCL, CRWV, IPWR"
    },
    "AMZN": {
        "lifts": [
            "NOW",
            "NOW.V",
            "CRWV",
            "IPWR",
            "SOFI",
            "ONDS"
        ],
        "reason": "AWS cloud + power chips"
    },
    "PLTR": {
        "lifts": [
            "BBAI",
            "NOW",
            "NOW.V"
        ],
        "reason": "Gov AI - PLTR pulls BBAI"
    },
    "MU": {
        "lifts": [
            "DRAM",
            "RAM"
        ],
        "reason": "DRAM leader - MU up lifts DRAM/RAM"
    },
    "NVDA": {
        "lifts": [
            "DRAM",
            "CRWV",
            "AAOI",
            "TSLA",
            "SIMO"
        ],
        "reason": "NVDA drives memory/server/optics"
    },
    "FSLR": {
        "lifts": [
            "TE"
        ],
        "reason": "Solar leader lifts TE"
    },
    "OKLO": {
        "lifts": [
            "TE"
        ],
        "reason": "Nuclear for AI lifts TE"
    },
    "SMR": {
        "lifts": [
            "TE",
            "USAR"
        ],
        "reason": "SMR energy"
    },
    "LUNR": {
        "lifts": [
            "SPCE"
        ],
        "reason": "Space - NASA lifts SPCE"
    },
    "ASTS": {
        "lifts": [
            "SPCE"
        ],
        "reason": "Space"
    },
    "RKLB": {
        "lifts": [
            "SPCE",
            "LUNR"
        ],
        "reason": "Space leader"
    },
    "MP": {
        "lifts": [
            "USAR"
        ],
        "reason": "Rare Earth"
    },
    "ALB": {
        "lifts": [
            "USAR",
            "EBM",
            "LAC"
        ],
        "reason": "Lithium leader - lifts USAR,EBM,LAC"
    },
    "LEU": {
        "lifts": [
            "USAR",
            "EU"
        ],
        "reason": "Uranium"
    },
    "VRT": {
        "lifts": [
            "CRWV",
            "IREN"
        ],
        "reason": "AI infra - lifts CRWV, IREN"
    },
    "SMCI": {
        "lifts": [
            "CRWV",
            "DELL"
        ],
        "reason": "AI servers"
    },
    "AFRM": {
        "lifts": [
            "SOFI",
            "PYPL"
        ],
        "reason": "Fintech"
    },
    "AI": {
        "lifts": [
            "BBAI",
            "VERI"
        ],
        "reason": "Gov AI"
    },
    "LITE": {
        "lifts": [
            "POET",
            "AAOI",
            "ZETA"
        ],
        "reason": "Optics leader 800G lifts POET/AAOI"
    },
    "COHR": {
        "lifts": [
            "POET",
            "AAOI"
        ],
        "reason": "Optics"
    },
    "AVAV": {
        "lifts": [
            "ONDS",
            "RCAT",
            "VTIX"
        ],
        "reason": "Drone leader Pentagon lifts ONDS"
    }
}

DEFAULT_L3 = {
    "Energy-Metals": {
        "tickers": [
            "ALB",
            "CCJ",
            "DNN",
            "EU",
            "FCX",
            "LAC",
            "LEU",
            "NDM",
            "NOL",
            "NOU",
            "NOV",
            "RIG",
            "TE",
            "USAR",
            "UUUU"
        ],
        "keywords": [
            "lithium",
            "uranium",
            "copper",
            "critical mineral",
            "DOE",
            "Canada",
            "Canadian",
            "Cameco",
            "rare earth"
        ]
    },
    "Chip-Mfg": {
        "tickers": [
            "AMAT",
            "AMD",
            "ASML",
            "BB",
            "CEVA",
            "DRAM",
            "NVDA",
            "POET",
            "RAM",
            "SIMO",
            "SNDU",
            "SQNS",
            "TSM"
        ],
        "keywords": [
            "chip contract",
            "foundry",
            "semiconductor",
            "AI chip",
            "Canada"
        ]
    },
    "AI-Cooling": {
        "tickers": [
            "AMZN",
            "BITF",
            "CRWV",
            "DELL",
            "HIVE",
            "HIVE.TO",
            "HUT",
            "IREN",
            "MSFT",
            "NBIS",
            "NOW",
            "NOW.V",
            "ORCL",
            "SMCI",
            "VRT"
        ],
        "keywords": [
            "data center",
            "liquid cooling",
            "AI cooling",
            "Canada",
            "Hut 8",
            "Bitfarms",
            "CoreWeave"
        ]
    },
    "SSD-Storage": {
        "tickers": [
            "DRAM",
            "MU",
            "RAM",
            "SIMO",
            "SNDU",
            "STX",
            "WDC"
        ],
        "keywords": [
            "SSD",
            "NAND",
            "storage",
            "NVMe",
            "memory"
        ]
    },
    "Controller-Chip": {
        "tickers": [
            "AVGO",
            "CEVA",
            "MCHP",
            "MRVL",
            "SIMO",
            "SQNS",
            "SWKS"
        ],
        "keywords": [
            "SSD controller",
            "storage controller",
            "NVMe controller",
            "memory controller"
        ]
    },
    "SMR-Nuclear": {
        "tickers": [
            "CCJ",
            "CCJ.TO",
            "DNN",
            "EU",
            "NNE",
            "NOU",
            "OKLO",
            "SMR",
            "USAR"
        ],
        "keywords": [
            "SMR",
            "nuclear",
            "small modular reactor",
            "nuclear contract",
            "CNSC",
            "Canada"
        ]
    },
    "AI-Power": {
        "tickers": [
            "AQN",
            "BBAI",
            "BIP",
            "BITF",
            "EME",
            "ETN",
            "FTS",
            "HIVE",
            "HUBB",
            "HUT",
            "IPWR",
            "NOW",
            "NOW.V",
            "NPI.TO",
            "ORCL",
            "PLTR",
            "PYPL",
            "SOFI",
            "TSLA",
            "UBER",
            "VERI"
        ],
        "keywords": [
            "power infrastructure",
            "transformer",
            "grid upgrade",
            "data center power",
            "Canada",
            "Hydro",
            "AI power",
            "ServiceNow",
            "NOW Vertical"
        ]
    },
    "Optical": {
        "tickers": [
            "AAOI",
            "CIEN",
            "COHR",
            "FN",
            "LITE",
            "NOK",
            "POET",
            "ZETA"
        ],
        "keywords": [
            "optical transceiver",
            "CPO",
            "800G",
            "1.6T",
            "optical contract",
            "POET",
            "5G"
        ]
    },
    "Quantum": {
        "tickers": [
            "IONQ",
            "QBTS",
            "QUBT",
            "RGTI"
        ],
        "keywords": [
            "quantum contract",
            "quantum award",
            "DOE quantum",
            "Canada",
            "D-Wave"
        ]
    },
    "Space-Drones": {
        "tickers": [
            "AQB",
            "ASTS",
            "AVAV",
            "BBAI",
            "CRWV",
            "DVLT",
            "EBM",
            "ENSC",
            "LUNR",
            "MDA.TO",
            "MSS",
            "ONDS",
            "PLTR",
            "RCAT",
            "SPCE",
            "VTIX"
        ],
        "keywords": [
            "drone contract",
            "satellite contract",
            "Space Force",
            "space contract",
            "Pentagon drone",
            "CSA",
            "Canada",
            "Virgin Galactic"
        ]
    }
}

def load_json(path, default):
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            # Auto-upgrade if default is larger
            if isinstance(data, list) and isinstance(default, list):
                if len(default) > len(data):
                    print(f"Upgrading {path.name} from {len(data)} to {len(default)}")
                    path.write_text(json.dumps(default, indent=2), encoding='utf-8')
                    return default
            if isinstance(data, dict) and isinstance(default, dict):
                old_count = len(data)
                new_count = len(default)
                # For L3 check total tickers
                if "Energy-Metals" in data:
                    old_t = sum(len(v.get("tickers",[])) for v in data.values())
                    new_t = sum(len(v.get("tickers",[])) for v in default.values())
                    if new_t > old_t:
                        print(f"Upgrading {path.name} from {old_t} to {new_t} tickers")
                        path.write_text(json.dumps(default, indent=2), encoding='utf-8')
                        return default
            return data
        except Exception as e:
            print(f"Load error {e}")
            return default
    path.write_text(json.dumps(default, indent=2), encoding='utf-8')
    return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')

L1_PATH = WATCH_DIR / "L1_watchlist.json"
L2_PATH = WATCH_DIR / "L2_leaders.json"
L3_PATH = WATCH_DIR / "L3_sectors.json"

L1_WATCH = load_json(L1_PATH, DEFAULT_L1)
L2_LEADERS = load_json(L2_PATH, DEFAULT_L2)
L3_SECTORS = load_json(L3_PATH, DEFAULT_L3)

# Ensure QBTS fix and NOW preserved in L1
L1_WATCH = [t if t != "QSTS" else "QBTS" for t in L1_WATCH]
if "QSTS" in L1_WATCH:
    L1_WATCH = [t for t in L1_WATCH if t != "QSTS"]
if "QBTS" not in L1_WATCH:
    L1_WATCH.append("QBTS")
if "NOW" not in L1_WATCH:
    L1_WATCH.append("NOW")
if "NOW.V" not in L1_WATCH:
    L1_WATCH.append("NOW.V")
L1_WATCH = sorted(set(L1_WATCH))
save_json(L1_PATH, L1_WATCH)

# Fix L2 lifts QSTS->QBTS
for k in list(L2_LEADERS.keys()):
    lifts = L2_LEADERS[k].get("lifts", [])
    L2_LEADERS[k]["lifts"] = [t if t != "QSTS" else "QBTS" for t in lifts]
save_json(L2_PATH, L2_LEADERS)

sent_hashes = set()
cooldown = {}

def can_send(key, mins=10):
    now = time.time()
    if now - cooldown.get(key, 0) < mins*60:
        return False
    cooldown[key] = now
    return True

def is_dup(title):
    h = hashlib.md5(title.lower().strip().encode()).hexdigest()
    if h in sent_hashes:
        return True
    sent_hashes.add(h)
    return False

def tg(msg, chat_id=None):
    cid = chat_id or CHAT_ID
    if not TOKEN or not cid:
        print(f"[NO TOKEN] {msg[:150]}")
        return False
    safe = msg[:3900]
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          json={"chat_id": str(cid), "text": safe}, timeout=12)
        if r.status_code != 200:
            print(f"TG {r.status_code} FAILED: {r.text[:500]} | Msg: {safe[:80]}")
            if "chat not found" in r.text.lower():
                print(">>> TIP: Open Telegram and send /start to your bot first! <<<")
        else:
            print(f"TG {r.status_code} OK: {safe[:80]}")
        return r.status_code==200
    except Exception as e:
        print(f"TG Error {e}")
        return False

def get_finnhub_news(ticker, days=3):
    if not FINNHUB: return []
    to_d = datetime.now().strftime("%Y-%m-%d")
    from_d = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from={from_d}&to={to_d}&token={FINNHUB}"
    try:
        r = requests.get(url, timeout=12)
        data = r.json()
        if not isinstance(data, list): return []
        return [{"headline": x.get("headline",""), "url": x.get("url",""), "datetime": x.get("datetime",0), "summary": x.get("summary","")} for x in data[:5]]
    except:
        return []

def get_yahoo_news(ticker):
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        news = stock.news or []
        out=[]
        for n in news[:5]:
            title = n.get("title","") or (n.get("content",{}).get("title","") if isinstance(n.get("content"), dict) else "")
            url = n.get("link","") or n.get("url","")
            dt = n.get("providerPublishTime",0) or int(time.time())
            if title:
                out.append({"headline": title, "url": url, "datetime": dt})
        return out
    except:
        return []

def get_hybrid(ticker):
    news = get_finnhub_news(ticker)
    return news if news else get_yahoo_news(ticker)

GOV_KEYWORDS = ["contract", "award", "deal", "agreement", "DOE", "Pentagon", "federal", "government", "Space Force", "NASA", "Canada", "Canadian government", "NRCan", "CNSC", "CSA", "Government of Canada"]

def scan_L1():
    print(f"[{datetime.now()}] L1 Scan {len(L1_WATCH)}")
    for ticker in L1_WATCH:
        if not can_send(f"L1_{ticker}", 30): continue
        for n in get_hybrid(ticker)[:1]:
            title = n["headline"]
            if not title or is_dup(title): continue
            if time.time() - n["datetime"] > 2*24*3600: continue
            low = (title + " " + n.get("summary","")).lower()
            has_gov = any(k.lower() in low for k in GOV_KEYWORDS)
            pref = "🔥 L1 Gov" if has_gov else "📰 L1"
            tg(f"{pref} Ticker: {ticker}\n{title}\nLink: {n.get('url','')}")
            break

def scan_L2():
    print(f"[{datetime.now()}] L2 Leaders Scan {len(L2_LEADERS)}")
    for leader, info in L2_LEADERS.items():
        if not can_send(f"L2_{leader}", 30): continue
        for n in get_hybrid(leader)[:1]:
            title = n["headline"]
            if not title or is_dup(title): continue
            if time.time() - n["datetime"] > 2*24*3600: continue
            lifts = ", ".join(info["lifts"])
            tg(f"🚀 L2 Leader Lifts L1\nLeader: {leader}\n{title}\nWill lift: {lifts}\nReason: {info['reason']}\nLink: {n.get('url','')}")
            break

def scan_L3():
    print(f"[{datetime.now()}] L3 Sectors Scan {len(L3_SECTORS)}")
        for sector_name, sector_data in L3_SECTORS.items():
        tickers = sector_data["tickers"] if isinstance(sector_data, dict) else sector_data
        keywords = sector_data.get("keywords", [sector_name]) if isinstance(sector_data, dict) else [sector_name]
        for ticker in tickers:
            if not can_send(f"L3_{ticker}", 30): continue
            for n in get_hybrid(ticker)[:1]:
                title = n["headline"]
                if not title or is_dup(title): continue
                if time.time() - n["datetime"] > 2*24*3600: continue
                low = (title + " " + n.get("summary","")).lower()
                has_sector = any(k.lower() in low for k in keywords) or ticker.lower() in low
                    tg(f"L3 Sector {sector_name}\nTicker: {ticker}\n{title}\nLink: {n.get('url','')}")
                    break

scheduler = BackgroundScheduler()
scheduler.add_job(scan_L1, 'interval', minutes=5, id="L1")
scheduler.add_job(scan_L2, 'interval', minutes=5, id="L2")
scheduler.add_job(scan_L3, 'interval', minutes=10, id="L3")

def handle_telegram():
    if not TOKEN: 
        print("No TOKEN")
        return
    offset=0
    print("Telegram polling started")
    unique = len(set(L1_WATCH))
    tg(f"Linked Bot Started UNIFIED - L1 {len(L1_WATCH)} ({unique} unique) L2 {len(L2_LEADERS)} L3 {len(L3_SECTORS)} sectors 93 stocks NOW+NOW.V QBTS fixed - Webhook ready at /webhook/tradingview")
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
                chat_id = str(msg["chat"]["id"])
                text = msg.get("text","").strip()
                if not text: continue
                lower=text.lower()
                if lower.startswith("/start"):
                    tg(f"Linked Bot UNIFIED - TV + L1 L2 L3 - L1 {len(L1_WATCH)} L2 {len(L2_LEADERS)} L3 10 sectors 93 stocks NOW+NOW.V QBTS - Webhook POST /webhook/tradingview Body secret mysecret123 ticker price action buy", chat_id)
                elif lower.startswith("/list"):
                    parts=text.split()
                    layer=parts[1].upper() if len(parts)>1 else "ALL"
                    if layer=="L1":
                        tg(f"L1 {len(L1_WATCH)}: {', '.join(L1_WATCH)}", chat_id)
                    elif layer=="L2":
                        m=f"L2 {len(L2_LEADERS)}:\n"
                        for k,v in L2_LEADERS.items():
                            m+=f"{k} -> {', '.join(v['lifts'])}\n"
                        tg(m[:4000], chat_id)
                    elif layer=="L3":
                        m=f"L3 {len(L3_SECTORS)}:\n"
                        for k,v in L3_SECTORS.items():
                            m+=f"{k}: {', '.join(v['tickers'])}\n"
                        tg(m[:4000], chat_id)
                    else:
                        tg(f"ALL L1={len(L1_WATCH)} L2={len(L2_LEADERS)} L3={len(L3_SECTORS)}", chat_id)
                elif lower.startswith("/scan"):
                    parts=text.split()
                    layer=parts[1].upper() if len(parts)>1 else "ALL"
                    tg(f"Scanning {layer}", chat_id)
                    if layer=="L1": scan_L1()
                    elif layer=="L2": scan_L2()
                    elif layer=="L3": scan_L3()
                    else:
                        scan_L1(); scan_L2(); scan_L3()
                    tg(f"Scan {layer} Done", chat_id)
                elif lower.startswith("/test"):
                    parts=text.split()
                    if len(parts)>1:
                        t=parts[1].upper()
                        news=get_hybrid(t)
                        if news:
                            tg(f"Test {t}\n{news[0]['headline']}\n{news[0].get('url','')}", chat_id)
                        else:
                            tg(f"No news {t}", chat_id)
        except Exception as e:
            print(f"TG Error {e}")
            time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.start()
        print("Scheduler L1/L2/L3 started")
    t = threading.Thread(target=handle_telegram, daemon=True)
    t.start()
    print("Telegram thread started")
    yield
    scheduler.shutdown()

app = FastAPI(title="Linked Bot Unified 93 stocks", lifespan=lifespan)

@app.get("/")
def home():
    return {
        "status": "Linked UNIFIED 93 stocks - TV + L1/L2/L3 Canada",
        "L1": len(L1_WATCH),
        "L2": len(L2_LEADERS),
        "L3": len(L3_SECTORS),
        "unique": len(set(L1_WATCH)),
        "webhook": "/webhook/tradingview",
        "example": {"secret": "mysecret123", "ticker": "HUT", "price": "15.20", "action": "buy"}
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
        print(f"Webhook unauthorized: {data}")
        return {"unauthorized": 1}
    ticker = data.get("ticker","").split(":")[-1].strip().upper()
    if not ticker:
        ticker = data.get("symbol","").split(":")[-1].strip().upper()
    price = data.get("price","") or data.get("close","")
    action = data.get("action","signal")
    print(f"TV Alert: {ticker} {action} @ {price}")
    if not ticker:
        return {"error": "no ticker"}
    if not can_send(f"TV_{ticker}", 2):
        return {"cooldown": 1}
    news = get_hybrid(ticker)
    layer_info = ""
    if ticker in L1_WATCH:
        layer_info = "L1 Watchlist"
    elif ticker in L2_LEADERS:
        lifts = ", ".join(L2_LEADERS[ticker]["lifts"])
        layer_info = f"L2 Leader lifts {lifts}"
    else:
        for sec, sec_data in L3_SECTORS.items():
            if ticker in sec_data["tickers"] or ticker.replace(".TO","") in sec_data["tickers"]:
                layer_info = f"L3 {sec}"
                break
    if news and not is_dup(news[0]["headline"]):
        tg(f"TradingView + News Linked\nTicker: {ticker} - {action} @ {price}\nLayer: {layer_info}\n{news[0]['headline']}\nLink: {news[0].get('url','')}")
    else:
        tg(f"TradingView Signal No Fresh News\nTicker: {ticker} - {action} @ {price}\nLayer: {layer_info}\nNo news last 2 days but TV triggered")
    return {"ok": True, "ticker": ticker}

if __name__ == "__main__":
    import uvicorn
    print(f"Starting LINKED BOT UNIFIED on http://0.0.0.0:{PORT}")
    print(f"Webhook URL: http://YOUR_IP:{PORT}/webhook/tradingview")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
