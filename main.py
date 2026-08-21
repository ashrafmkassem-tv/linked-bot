"""
FINAL FIXED - L1+L2+L3+L4 TRUE LINKED - 95 stocks - NO BUG - Railway Ready
- Fixes: NameError ticker not defined (line 641 bug)
- L3: 10 sectors 95 tickers CBOE:SNDU + BOTH NOW
- L4: sector-to-sector linking + gov triggers
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

print(f"LINKED BOT UNIFIED L3+L4 FIXED - TOKEN:{bool(TOKEN)} CHAT:{CHAT_ID} FINNHUB:{bool(FINNHUB)} PORT:{PORT}")

DEFAULT_L1 = ['AAOI','ALB','AMAT','AMD','AMZN','AQB','ASML','ASTS','AVGO','BBAI','CCJ','CEVA','CIEN','COHR','CRWV','DELL','DRAM','DVLT','EBM','ENSC','EU','LAC','LEU','LITE','LUNR','MCHP','MRVL','MSFT','MSS','MU','NBIS','NNE','NOK','NOW','NVDA','OKLO','ONDS','ORCL','PLTR','POET','PYPL','QBTS','QUBT','RAM','RGTI','RIG','SIMO','SMCI','SMR','SNDU','SNDK','SOFI','SPCE','STX','TE','TSLA','USAR','UUUU','VERI','VRT','VTIX','WDC','ZETA','ANET','MOD','CLS','PSTG','NTAP','ON','NXPI','ARM','QCOM','IONQ','RKLB','LUNR','PL','BKSY','RDW','IBM','GOOGL','HON','AAOI','POET','NOK','FN','CIEN','LUMN','ENSC','IREN','NDM','NOU','EBM','MP','ALB','CCJ','MSS','SPCE','RKLB','ASTS','VTIX','DVLT','NBIS','ANET','VRT','SMCI','DELL','PLTR','VERI','SOFI','IPWR','TSLA','NVDA','AMZN','MSFT','PYPL','ZETA','BBAI','ORCL','UBER','NOW','SIMO','CEVA','MRVL','MCHP','ON','NXPI','ARM','QCOM','QBTS','IONQ','RGTI','QUBT','ARQQ','IBM','GOOGL','HON','SQNS','AMD','AVGO','ASML','LRCX','KLAC','SNPS']

def load_unified():
    for p in [BASE_DIR/"watchlists"/"L3_L4_UNIFIED_95_PERFECT.json", BASE_DIR/"L3_L4_UNIFIED_95_PERFECT.json", BASE_DIR/"watchlists"/"L3_sectors.json", BASE_DIR/"L3_sectors.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if "sectors" in data:
                    print(f"L3_L4 UNIFIED loaded from {p.name}: {data.get('total_tickers',0)} tickers, {data.get('total_sectors',0)} sectors + L4 links")
                    return data
                if isinstance(data, dict) and len(data)>=5 and all(isinstance(v,list) for v in data.values()):
                    total = sum(len(v) for v in data.values())
                    print(f"L3 loaded from {p.name}: {total} tickers, {len(data)} sectors - building L4 links")
                    return {
                        "version":"L3_to_L4",
                        "total_tickers":total,
                        "total_sectors":len(data),
                        "sectors":data,
                        "sector_links":{"SSD_Storage":["AI_Cooling","Controller_Chip","Chip_Mfg"],"AI_Cooling":["SSD_Storage","AI_Power","Chip_Mfg"],"AI_Power":["AI_Cooling","Controller_Chip","Chip_Mfg","Quantum"],"Controller_Chip":["Chip_Mfg","SSD_Storage","AI_Cooling"],"Chip_Mfg":["Controller_Chip","SSD_Storage","Optical"],"Optical":["Chip_Mfg","Space_Drones"],"SMR_Nuclear":["Energy_Metals","AI_Power"],"Energy_Metals":["SMR_Nuclear","AI_Power"],"Space_Drones":["Optical","Energy_Metals"],"Quantum":["AI_Power","Chip_Mfg"]},
                        "gov_triggers":{"AI":["AI_Power","AI_Cooling","Controller_Chip","Chip_Mfg","Quantum"],"Nuclear":["SMR_Nuclear","Energy_Metals"],"Space":["Space_Drones","Optical"],"Storage":["SSD_Storage","Chip_Mfg"]},
                        "layer_info":{}
                    }
            except Exception as e:
                print(f"Load fail {p}: {e}")
    return {"sectors":{},"sector_links":{},"gov_triggers":{}}

UNIFIED = load_unified()
L3_SECTORS = UNIFIED.get("sectors",{})
SECTOR_LINKS = UNIFIED.get("sector_links",{})
GOV_TRIGGERS = UNIFIED.get("gov_triggers",{})

all_tvs = [t for lst in L3_SECTORS.values() for t in lst]
plain_all = [tv.split(":")[-1] for tv in all_tvs]
L1_WATCH = sorted(list(set(DEFAULT_L1 + plain_all)))[:95]

L2_LEADERS = {"NVDA":{"lifts":["DRAM","CRWV","AAOI"],"reason":"NVDA drives"},"MSFT":{"lifts":["NOW","ORCL","CRWV"],"reason":"AI cloud"},"MU":{"lifts":["DRAM","RAM","SNDU"],"reason":"DRAM leader"},"LITE":{"lifts":["POET","AAOI"],"reason":"Optics"},"SMCI":{"lifts":["CRWV","DELL"],"reason":"AI servers"}}

print(f"L1 {len(L1_WATCH)} unique, L2 {len(L2_LEADERS)}, L3 {len(L3_SECTORS)} sectors {sum(len(v) for v in L3_SECTORS.values())} tickers, L4 {len(SECTOR_LINKS)} links")

_last = {}
_seen=set()
def can_send(k, mins=30):
    from datetime import datetime, timedelta
    now=datetime.utcnow()
    if k in _last and now-_last[k] < timedelta(minutes=mins): return False
    _last[k]=now
    return True
def is_dup(h):
    import hashlib
    hd=hashlib.md5(h.encode()).hexdigest()
    if hd in _seen: return True
    _seen.add(hd)
    if len(_seen)>500: _seen.clear()
    return False
def tg(text, chat_id=None):
    cid=chat_id or CHAT_ID
    if not TOKEN or not cid: 
        print(f"TG skip: {text[:80]}")
        return
    try:
        r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id":cid,"text":text[:4000],"disable_web_page_preview":True}, timeout=10)
        print(f"TG {r.status_code} OK: {text[:80]}")
    except Exception as e:
        print(f"TG Error {e}")

def get_hybrid(ticker):
    if not FINNHUB: return []
    try:
        clean=ticker.split(":")[-1].replace(".V","").replace(".TO","")
        url=f"https://finnhub.io/api/v1/company-news?symbol={clean}&from={(datetime.utcnow()-timedelta(days=2)).strftime('%Y-%m-%d')}&to={datetime.utcnow().strftime('%Y-%m-%d')}&token={FINNHUB}"
        r=requests.get(url, timeout=10)
        if r.status_code==200:
            data=r.json()
            news=[]
            for n in data[:3]:
                if n.get("headline"):
                    news.append({"headline":n["headline"],"url":n.get("url","")})
            return news
    except: pass
    return []

def scan_L1():
    print(f"[{datetime.now()}] L1 Scan {len(L1_WATCH)}")
    for ticker in L1_WATCH:
        if not can_send(f"L1_{ticker}", 60): continue
        news=get_hybrid(ticker)
        if news and not is_dup(news[0]["headline"]):
            tg(f"📈 L1 Ticker: {ticker}\n{news[0]['headline']}\nLink: {news[0].get('url','')}")

def scan_L2():
    print(f"[{datetime.now()}] L2 Leaders Scan {len(L2_LEADERS)}")
    for leader, info in L2_LEADERS.items():
        if not can_send(f"L2_{leader}", 60): continue
        news=get_hybrid(leader)
        if news and not is_dup(news[0]["headline"]):
            tg(f"🚀 L2 Leader: {leader} -> lifts {', '.join(info['lifts'])}\nReason: {info['reason']}\n{news[0]['headline']}\nLink: {news[0].get('url','')}")

def scan_L3():
    # FIXED - NO MORE NameError
    total=sum(len(v) for v in L3_SECTORS.values())
    print(f"[{datetime.now()}] L3 Sectors Scan {len(L3_SECTORS)} - {total} total tickers")
    for sector_name, tickers in L3_SECTORS.items():
        if not tickers: continue
        if isinstance(tickers, dict):
            tickers = tickers.get("tickers", [])
        for tv in tickers[:2]:
            plain = tv.split(":")[-1].replace(".V","").replace(".TO","")
            if not can_send(f"L3_{sector_name}_{plain}", 120): continue
            news=get_hybrid(plain)
            if news and not is_dup(news[0]["headline"]):
                tg(f"🏭 L3 Sector: {sector_name}\nTicker: {tv} ({plain})\nGov News: {news[0]['headline']}\nLink: {news[0].get('url','')}\nSector size: {len(tickers)}")

def scan_L4():
    print(f"[{datetime.now()}] L4 TRUE LINKED Scan {len(SECTOR_LINKS)} links, {len(GOV_TRIGGERS)} gov triggers")
    for gov_key, linked_sectors in GOV_TRIGGERS.items():
        if not can_send(f"L4_GOV_{gov_key}", 180): continue
        triggered=[]
        for sector in linked_sectors:
            sec_tickers=L3_SECTORS.get(sector,[])
            if not sec_tickers: continue
            for tv in sec_tickers[:1]:
                plain=tv.split(":")[-1].replace(".V","").replace(".TO","")
                news=get_hybrid(plain)
                if news and gov_key.lower() in news[0]["headline"].lower():
                    triggered.append((sector,tv,news[0]))
                    break
        if triggered:
            all_affected=set(linked_sectors)
            for sec,_,_ in triggered:
                all_affected.update(SECTOR_LINKS.get(sec,[]))
            sectors_str=", ".join(sorted(all_affected))
            first=triggered[0]
            if not is_dup(first[2]["headline"]+gov_key):
                tg(f"🔗 L4 TRUE LINKED - Gov: {gov_key.upper()}\nTriggered: {first[0]} ({first[1]})\nAll Linked Sectors: {sectors_str}\nNews: {first[2]['headline']}\nLink: {first[2].get('url','')}\nTotal affected: {len(all_affected)}")

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
    tg(f"Linked Bot Started FIXED L3+L4 TRUE LINKED - L1 {len(L1_WATCH)} L2 {len(L2_LEADERS)} L3 {len(L3_SECTORS)} sectors {sum(len(v) for v in L3_SECTORS.values())} stocks L4 {len(SECTOR_LINKS)} links CBOE:SNDU BOTH NOW FIXED - No Bug")
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset":offset,"timeout":30}, timeout=35)
            data=r.json()
            if not data.get("ok"):
                time.sleep(5)
                continue
            for upd in data.get("result",[]):
                offset=upd["update_id"]+1
                msg=upd.get("message") or upd.get("edited_message")
                if not msg: continue
                text=msg.get("text","").strip()
                if not text: continue
                if text.lower().startswith("/start"):
                    tg(f"Linked Bot UNIFIED L3+L4 FIXED - L1 {len(L1_WATCH)} L2 {len(L2_LEADERS)} L3 {len(L3_SECTORS)} L4 {len(SECTOR_LINKS)}", msg["chat"]["id"])
        except Exception as e:
            print(f"TG Error {e}")
            time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.start()
        print("Scheduler L1/L2/L3/L4 started")
    t=threading.Thread(target=handle_telegram, daemon=True)
    t.start()
    print("Telegram thread started")
    yield
    scheduler.shutdown()

app=FastAPI(title="Linked Bot FIXED L3+L4", lifespan=lifespan)

@app.get("/")
def home():
    return {"status":f"Linked FIXED L3+L4 {sum(len(v) for v in L3_SECTORS.values())} stocks","L1":len(L1_WATCH),"L2":len(L2_LEADERS),"L3":len(L3_SECTORS),"L4_links":len(SECTOR_LINKS),"total":sum(len(v) for v in L3_SECTORS.values())}

@app.post("/webhook/tradingview")
async def webhook(req: Request):
    try:
        data=await req.json()
    except:
        body=await req.body()
        try:
            data=json.loads(body.decode())
        except:
            data={}
    if data.get("secret") != WEBHOOK_SECRET:
        return {"unauthorized":1}
    ticker=data.get("ticker","").split(":")[-1].strip().upper()
    if not ticker:
        ticker=data.get("symbol","").split(":")[-1].strip().upper()
    price=data.get("price","") or data.get("close","")
    action=data.get("action","signal")
    if not ticker: return {"error":"no ticker"}
    if not can_send(f"TV_{ticker}",2): return {"cooldown":1}
    news=get_hybrid(ticker)
    layer_info="L1"
    for sec, sec_tickers in L3_SECTORS.items():
        plains=[t.split(":")[-1] for t in sec_tickers]
        if ticker in plains:
            linked=SECTOR_LINKS.get(sec,[])
            layer_info=f"L3 {sec} | L4 links -> {', '.join(linked[:3])}"
            break
    if news and not is_dup(news[0]["headline"]):
        tg(f"TV + News L3+L4 LINKED\nTicker: {ticker} - {action} @ {price}\nLayer: {layer_info}\n{news[0]['headline']}\nLink: {news[0].get('url','')}")
    else:
        tg(f"TV Signal L3+L4\nTicker: {ticker} - {action} @ {price}\nLayer: {layer_info}")
    return {"ok":True,"ticker":ticker}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
