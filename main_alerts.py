
# DIRECT MODE V6 - PRE-EXPLOSION LIGHT MODE - هدفنا نمسك السهم قبل ما يفرقع
# تخفيف الشروط + تبطيء + حماية 403
# كان الهدف من البداية: flat + squeeze + RSI بيبني + حجم بيبتدي يزيد = انفجار قريب

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

finnhub_403_count = 0
last_403_alert = None

def load_sectors():
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
def can_send(k, mins=60):  # قللت من 90 ل 60 عشان تلحق الفرصة تاني
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
    global finnhub_403_count, last_403_alert
    if not FINNHUB: 
        print("[ERR] FINNHUB key missing")
        return None
    try:
        clean = sym.split(":")[-1].replace(".V","").replace(".TO","").upper()
        to_ts = int(datetime.now(ZoneInfo("UTC")).timestamp())
        from_ts = int((datetime.now(ZoneInfo("UTC"))-timedelta(days=days)).timestamp())
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={clean}&resolution=D&from={from_ts}&to={to_ts}&token={FINNHUB}"
        r=requests.get(url, timeout=12)

        if r.status_code == 403 or r.status_code == 401:
            finnhub_403_count += 1
            print(f"[FINNHUB {r.status_code} AUTH FAIL] {clean} - Count {finnhub_403_count}")
            now = datetime.now(ET_ZONE)
            if last_403_alert is None or (now - last_403_alert) > timedelta(minutes=60):
                tg(f"⚠️ FINNHUB KEY FAILED {r.status_code}\nالكي {FINNHUB[:6]}... اترفض\nTime: {now.strftime('%Y-%m-%d %H:%M ET')}")
                last_403_alert = now
            return None

        if r.status_code == 429:
            print(f"[FINNHUB 429] {clean} - sleeping 5s")
            time.sleep(5)
            return None

        if r.status_code!=200: 
            print(f"[FINNHUB {r.status_code}] {clean}")
            return None
        d=r.json()
        if d.get("s")!="ok" or not d.get("c"): return None
        if finnhub_403_count > 0:
            finnhub_403_count = 0
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
    return {"width":width,"pct":pct, "upper":up, "lower":lo, "mid":s}

def rvol_calc(vols,per=20):
    if len(vols)<per+1: return 1.0
    avg=sum(vols[-per-1:-1])/per
    return vols[-1]/avg if avg!=0 else 1.0

def sma(prices, per=20):
    if len(prices) < per: return None
    return sum(prices[-per:])/per

# ================= V6 PRE-EXPLOSION LOGIC - LIGHTENED =================
def analyze_prepare(ticker):
    daily=get_candles(ticker,80)
    if not daily or len(daily["c"])<30: 
        return None
    c=daily["c"]; v=daily["v"]
    price=c[-1]; prev=c[-2]
    chg=(price-prev)/prev*100 if prev!=0 else 0

    # 1. FLATNESS - وسعنا من 0.8% ل 2.0% عشان نلقط اللي بيجهز
    # كان: -0.8 to 0.8 فقط
    # بقى: -2.0 to 2.0 مثالي، لحد 3% مقبول
    flat_score = 0
    abs_chg = abs(chg)
    if abs_chg <= 1.2:
        flat_score = 30  # مثالي - لسه مجمع
    elif abs_chg <= 2.0:
        flat_score = 20  # كويس - بيبتدي يتحرك
    elif abs_chg <= 3.0:
        flat_score = 10  # مقبول - بداية انفجار خفيف
    else:
        return None  # طار خلاص مش هنلحقه

    # فلتر اضافي: آخر 3 ايام كلهم flat نسبيا؟ ده squeeze حقيقي
    last_3_chg = []
    for i in range(1,4):
        if len(c) > i:
            ch = abs((c[-i]-c[-i-1])/c[-i-1]*100) if c[-i-1]!=0 else 100
            last_3_chg.append(ch)
    avg_3d_volatility = sum(last_3_chg)/len(last_3_chg) if last_3_chg else 100
    if avg_3d_volatility > 4.0:
        return None  # متذبذب جامد مش تجميع

    # 2. RSI - وسعنا من 50-56 ل 45-65 عشان نمسك البناء بدري
    rsi=rsi_calc(c)
    rsi_score = 0
    if 50 <= rsi <= 60:
        rsi_score = 25  # مثالي - قوة شرائية بتبني
    elif 45 <= rsi <= 65:
        rsi_score = 20  # كويس
    elif 40 <= rsi <= 70:
        rsi_score = 10  # مقبول - لسه مش overbought
    else:
        return None  # يا ضعيف جدا يا overbought خلاص

    # 3. BOLLINGER SQUEEZE - اهم حاجة للانفجار
    # كان: 0.05 فقط
    # بقى: لحد 0.15 مقبول
    bb=bollinger(c)
    if not bb: return None
    bb_score = 0
    if bb["width"] <= 0.06:
        bb_score = 30  # squeeze قوي جدا - انفجار قريب جدا
    elif bb["width"] <= 0.10:
        bb_score = 20  # squeeze كويس
    elif bb["width"] <= 0.15:
        bb_score = 10  # بداية squeeze
    else:
        return None  # مفتوح جامد مش هيفرقع دلوقتي

    # بونص: السعر قريب من الـ upper band؟ معناه بيحاول يخترق
    if 0.6 <= bb["pct"] <= 0.95:
        bb_score += 5

    # 4. VOLUME - قللنا من 1.2 ل 0.9 عشان نلقط بدري قبل ما الحجم ينفجر
    rv=rvol_calc(v)
    rvol_score = 0
    if rv >= 1.3:
        rvol_score = 20  # حجم انفجر - دخل
    elif rv >= 1.0:
        rvol_score = 15  # حجم بيزيد - بيجهز
    elif rv >= 0.8:
        rvol_score = 10  # حجم طبيعي - لسه بدري
    else:
        rvol_score = 5   # حتى لو حجم قليل بنقبله في التجميع

    # 5. SMA FILTER - اضافة جديدة: السعر فوق متوسط 20 يوم؟ معناه اتجاه صاعد
    sma20 = sma(c, 20)
    sma_bonus = 0
    if sma20 and price > sma20:
        sma_bonus = 5
        # لو فوق SMA20 بـ 5% بس، لسه بدري
        if price < sma20 * 1.08:
            sma_bonus += 5

    total_score = flat_score + rsi_score + bb_score + rvol_score + sma_bonus

    # كان: 65 - بقى 55 عشان نلقط اكتر
    if total_score < 55:
        return None

    # حساب الاهداف - قبل الانفجار
    stop = price * 0.965  # 3.5%
    # اهداف اكبر عشان انفجار
    t1 = price * 1.15
    t2 = price * 1.30
    t3 = price * 1.50

    return {
        "symbol":ticker,
        "price":price,
        "chg":chg,
        "score":total_score,
        "rsi":rsi,
        "rvol":rv,
        "bb":bb["width"],
        "bb_pct":bb["pct"],
        "avg3d":avg_3d_volatility,
        "stop":stop,
        "t1":t1,
        "t2":t2,
        "t3":t3,
        "details": f"Flat{flat_score}+RSI{rsi_score}+BB{bb_score}+Vol{rvol_score}+SMA{sma_bonus}"
    }

scheduler=BackgroundScheduler()

def direct_scan_98(bypass_market=False):
    global finnhub_403_count
    WATCH = WATCH_LIST
    now_et=datetime.now(ET_ZONE)
    ts=now_et.strftime("%Y-%m-%d %H:%M:%S")
    if not WATCH:
        print(f"[{ts} ET] DIRECT SCAN 0 - EMPTY WATCH LIST!")
        tg(f"⚠️ WATCH LIST EMPTY at {ts} ET")
        return
    if not bypass_market and not is_market_hours():
        print(f"[{ts} ET] DIRECT SCAN {len(WATCH)} - Skip outside 09:00-16:00 ET")
        return

    if finnhub_403_count >= 5:
        print(f"[{ts} ET] SKIP due to {finnhub_403_count} AUTH FAILS")
        return

    print(f"[{ts} ET] DIRECT SCAN {len(WATCH)} - START {len(WATCH)} - PRE-EXPLOSION LIGHT MODE - 1.2s delay")
    found=0
    fails=0
    finnhub_403_count = 0

    for idx, t in enumerate(WATCH):
        try:
            res=analyze_prepare(t)
            if not res: 
                if finnhub_403_count > 0:
                    fails+=1
                    if finnhub_403_count >= 3:
                        print(f"[{ts} ET] Aborting after {finnhub_403_count} FAILS")
                        break
                time.sleep(1.2)
                continue
            key=f"PREPARE_{res['symbol']}"
            if not can_send(key,60): 
                time.sleep(1.2)
                continue
            found+=1
            # رسالة جديدة توضح انه قبل الانفجار
            msg=(f"🚀 PRE-EXPLOSION: {res['symbol']} ${res['price']:.2f} ({res['chg']:+.2f}%) Score {res['score']}/100\n"
                 f"📊 {res['details']}\n"
                 f"Flat {res['chg']:+.2f}% | RSI {res['rsi']:.1f} | rVol {res['rvol']:.2f}x | BB {res['bb']:.3f} ({res['bb_pct']*100:.0f}%) | 3dAvg {res['avg3d']:.2f}%\n"
                 f"🎯 Entry ${res['price']:.2f} → ${res['t1']:.2f} / ${res['t2']:.2f} / ${res['t3']:.2f} | Stop ${res['stop']:.2f}")
            tg(msg)
            time.sleep(1.2)
        except Exception as e:
            print(f"Scan err {t}: {e}")
            time.sleep(1.2)

    print(f"[{ts} ET] DIRECT SCAN {len(WATCH)} - Done Found {found} - Fails {fails} - 403Count {finnhub_403_count} - LIGHT MODE")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.add_job(lambda: direct_scan_98(False),'interval',minutes=15,id='scan98')
        scheduler.start()
        print(f"Scheduler DIRECT SCAN {len(WATCH_98)} every 15min - 09:00-16:00 ET - V6 PRE-EXPLOSION LIGHT")
        tg(f"✅ Linked-Bot V6 PRE-EXPLOSION Started: {len(WATCH_98)} tickers - {datetime.now(ET_ZONE).strftime('%Y-%m-%d %H:%M ET')}\nLight Mode: Flat ±2%, BB 0.15, RSI 45-65, Score 55, 1.2s delay")
    yield
    scheduler.shutdown()

app=FastAPI(title=f"DIRECT {len(WATCH_LIST)} PRE-EXPLOSION V6 LIGHT", lifespan=lifespan)

@app.get("/")
def home():
    return {"status":f"DIRECT {len(WATCH_98)} PRE-EXPLOSION LIGHT","market_open":is_market_hours(),"et_now":datetime.now(ET_ZONE).isoformat(), "watch_count": len(WATCH_98), "finnhub_403_count": finnhub_403_count}

@app.get("/health")
def health():
    return {"ok":True,"count":len(WATCH_LIST),"market_open":is_market_hours(),"rig":"RIG" in WATCH_LIST, "tickers": WATCH_LIST, "last_alerts": list(_last.keys())[-10:], "finnhub_key_prefix": FINNHUB[:6]+"..." if FINNHUB else "MISSING", "finnhub_403_count": finnhub_403_count}

@app.get("/scan")
def manual():
    threading.Thread(target=lambda: direct_scan_98(True),daemon=True).start()
    return {"started":f"DIRECT SCAN {len(WATCH_98)} - V6 LIGHT - bypass market"}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=PORT)

