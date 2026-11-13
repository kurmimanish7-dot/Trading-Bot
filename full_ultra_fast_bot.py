# -*- coding: utf-8 -*-
"""
FULL FEATURES ULTRA-FAST BOT - Slow Network Edition
Pura bot: NIFTY + BANKNIFTY + FINNIFTY + MIDCPNIFTY + SENSEX + BANKEX + Equity + GEX + OTR + Paper Trade
Par loading ultra-fast kyunki:
1. Start me sirf streamlit + stdlib - pandas/numpy/requests ZERO
2. Load pe 0 API call - jo tab khologe wahi load hoga (lazy)
3. Scan All bhi 1-1 karke, parallel nahi
4. Har fetch 2.5 sec timeout + cache + fallback
5. FINNIFTY bug fixed - NIFTY_FIN_SERVICE.NS
USE: streamlit run full_ultra_fast_bot.py
"""
import time, json, math
from datetime import datetime as dt
from zoneinfo import ZoneInfo
import urllib.request, urllib.parse
import streamlit as st

IST = ZoneInfo("Asia/Kolkata")

INDEX_META = {
    "NIFTY": {"yahoo": "^NSEI", "nse": "NIFTY 50", "lot": 65, "step": 50, "range": (15000, 35000)},
    "BANKNIFTY": {"yahoo": "^NSEBANK", "nse": "NIFTY BANK", "lot": 30, "step": 100, "range": (40000, 80000)},
    "FINNIFTY": {"yahoo": "NIFTY_FIN_SERVICE.NS", "nse": "NIFTY FIN SERVICE", "lot": 60, "step": 50, "range": (15000, 40000)},
    "MIDCPNIFTY": {"yahoo": "NIFTY_MIDCAP_100.NS", "nse": "NIFTY MID SELECT", "lot": 120, "step": 25, "range": (8000, 20000)},
    "SENSEX": {"yahoo": "^BSESN", "nse": "SENSEX", "lot": 20, "step": 100, "range": (60000, 110000)},
    "BANKEX": {"yahoo": "^BSEBANK", "nse": "BANKEX", "lot": 30, "step": 100, "range": (40000, 80000)},
}
TF_MAP = {
    "5m": {"yf_int": "5m", "yf_range": "1d", "label": "5 Min"},
    "15m": {"yf_int": "15m", "yf_range": "5d", "label": "15 Min"},
    "1h": {"yf_int": "60m", "yf_range": "5d", "label": "1 Hour"},
}

st.set_page_config(page_title="Full Bot Ultra Fast", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>div[data-testid='stMetric']{background:#0e1117;border:1px solid #262730;border-radius:8px;padding:6px} .small{font-size:12px;color:#888}</style>", unsafe_allow_html=True)
st.markdown("## ⚡ Full Bot - Ultra Fast")
st.caption("Pura features • Lazy loading • Slow network ready • FINNIFTY fix included")

def _http_json(url, timeout=2.5):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))

@st.cache_data(ttl=5, show_spinner=False)
def fetch_spot(sym):
    meta = INDEX_META.get(sym)
    if not meta:
        return {"price": None, "source": "NO_META"}
    t0 = time.time()
    for base in ["https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com"]:
        try:
            j = _http_json(f"{base}/v8/finance/chart/{meta['yahoo']}?interval=1m&range=1d", timeout=2.5)
            p = float(j["chart"]["result"][0]["meta"].get("regularMarketPrice") or 0)
            lo, hi = meta["range"]
            if lo <= p <= hi:
                return {"price": p, "source": "YAHOO", "ms": int((time.time()-t0)*1000)}
        except Exception:
            continue
    return {"price": None, "source": "FAILED", "ms": int((time.time()-t0)*1000)}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_candles(sym, tf="15m"):
    meta = INDEX_META.get(sym)
    if not meta:
        return []
    cfg = TF_MAP.get(tf, TF_MAP["15m"])
    try:
        j = _http_json(f"https://query2.finance.yahoo.com/v8/finance/chart/{meta['yahoo']}?interval={cfg['yf_int']}&range={cfg['yf_range']}", timeout=3)
        res = j["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        out = []
        for i in range(len(res.get("timestamp", []))):
            try:
                c = q["close"][i]
                if c is None:
                    continue
                c = float(c)
                out.append({"o": float(q["open"][i] or c), "h": float(q["high"][i] or c), "l": float(q["low"][i] or c), "c": c, "v": float(q["volume"][i] or 0)})
            except Exception:
                continue
        return out
    except Exception:
        return []

@st.cache_data(ttl=30, show_spinner=False)
def fetch_chain_lite(sym):
    # NSE chain via proxy, pandas ke bina - PCR + GEX + Max Pain ke liye
    try:
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={sym}"
        proxy = "https://api.allorigins.win/raw?url=" + urllib.parse.quote(url, safe="")
        j = _http_json(proxy, timeout=4)
        rec = j.get("records", {})
        items = rec.get("data", [])
        if not items:
            return {"rows": [], "expiries": rec.get("expiryDates", []), "source": "EMPTY"}
        # pehli expiry lo
        exps = rec.get("expiryDates", [])
        if not exps:
            return {"rows": [], "expiries": [], "source": "NO_EXP"}
        target = exps[0]
        rows = []
        for it in items:
            if it.get("expiryDate") != target:
                continue
            s = float(it.get("strikePrice") or 0)
            for typ in ["CE", "PE"]:
                d = it.get(typ)
                if isinstance(d, dict):
                    rows.append({"strike": s, "type": typ, "oi": float(d.get("openInterest") or 0), "ltp": float(d.get("lastPrice") or 0), "iv": float(d.get("impliedVolatility") or 0)})
        return {"rows": rows, "expiries": exps, "source": "NSE_PROXY", "expiry": target}
    except Exception as e:
        return {"rows": [], "expiries": [], "source": f"FAIL {str(e)[:30]}"}

def ema_calc(vals, span):
    if not vals:
        return None
    k = 2.0/(span+1)
    e = vals[0]
    for v in vals[1:]:
        e = v*k + e*(1-k)
    return e

def calc_indicators(candles, spot):
    if len(candles) < 10:
        return {"support": spot*0.998, "resistance": spot*1.002, "vwap": spot, "ema20": spot, "ema50": spot, "rsi": 50, "atr": spot*0.004, "day_open": spot, "orb_h": spot, "orb_l": spot}
    closes = [c["c"] for c in candles]
    last30 = candles[-30:]
    support = min(c["l"] for c in last30)
    resistance = max(c["h"] for c in last30)
    tpv = sum(((c["h"]+c["l"]+c["c"])/3)*max(c["v"],1) for c in candles)
    vol = sum(max(c["v"],1) for c in candles)
    vwap = tpv/vol if vol else spot
    ema20 = ema_calc(closes, 20); ema50 = ema_calc(closes, 50)
    gains=[]; losses=[]
    for i in range(1, min(15, len(closes))):
        d = closes[-i]-closes[-i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag = sum(gains)/14 if gains else 0; al = sum(losses)/14 if losses else 0
    rsi = 100-(100/(1+(ag/al))) if al>0 else 70
    atr = abs(resistance-support)/6 if resistance>support else spot*0.004
    day_open = candles[0]["o"]
    orb = candles[:3]
    orb_h = max(c["h"] for c in orb) if orb else spot
    orb_l = min(c["l"] for c in orb) if orb else spot
    return {"support": support, "resistance": resistance, "vwap": vwap, "ema20": ema20, "ema50": ema50, "rsi": rsi, "atr": atr, "day_open": day_open, "orb_h": orb_h, "orb_l": orb_l}

def calc_setup(sym, spot, ind, chain=None):
    expected = 150.0
    gamma_flip = 0; max_pain = spot; pcr = None; call_wall = spot+200; put_wall = spot-200; net_gex = 0
    if chain and chain.get("rows"):
        rows = chain["rows"]
        ce = [r for r in rows if r["type"]=="CE"]; pe = [r for r in rows if r["type"]=="PE"]
        ce_oi = sum(r["oi"] for r in ce); pe_oi = sum(r["oi"] for r in pe)
        if ce_oi>0:
            pcr = round(pe_oi/ce_oi, 2)
        # Max Pain
        strikes = sorted(set(r["strike"] for r in rows))
        best=None; best_loss=1e18
        for s in strikes:
            loss = sum(max(0, s-r["strike"])*r["oi"] for r in ce) + sum(max(0, r["strike"]-s)*r["oi"] for r in pe)
            if loss < best_loss:
                best_loss=loss; best=s
        if best:
            max_pain = best
        if ce:
            call_wall = max(ce, key=lambda x: x["oi"])["strike"]
        if pe:
            put_wall = max(pe, key=lambda x: x["oi"])["strike"]
        # Expected move from ATM straddle
        atm = min(strikes, key=lambda x: abs(x-spot)) if strikes else spot
        ce_atm = next((r for r in ce if r["strike"]==atm), None)
        pe_atm = next((r for r in pe if r["strike"]==atm), None)
        if ce_atm and pe_atm:
            expected = round(0.80*(ce_atm["ltp"]+pe_atm["ltp"]),1) if (ce_atm["ltp"]+pe_atm["ltp"])>0 else expected
            gamma_flip = atm
    else:
        expected = max(round(ind["atr"]*1.2,1), 30)
    support_ok = (ind["support"] < spot and abs(spot-ind["support"])/spot <= 0.03)
    resist_ok = (ind["resistance"] > spot and abs(ind["resistance"]-spot)/spot <= 0.03)
    bullish = spot > ind["vwap"] and spot > ind["ema20"]
    if bullish:
        sl = ind["support"] if support_ok else spot - expected*0.5
        risk = max(spot-sl, 1.0)
        t1 = min(spot + expected*0.618, call_wall if chain and chain.get("rows") else spot+expected*0.618)
        t2 = spot + expected*1.0
        action = "BUY"
    else:
        sl = ind["resistance"] if resist_ok else spot + expected*0.5
        risk = max(sl-spot, 1.0)
        t1 = max(spot - expected*0.618, put_wall if chain and chain.get("rows") else spot-expected*0.618)
        t2 = spot - expected*1.0
        action = "SELL"
    rr = round(abs(t1-spot)/risk,2) if risk else 0
    kelly = 0
    if rr>0:
        kelly = round(max(0, min(((0.60*rr-0.40)/rr/4), 0.25))*100,2)
    return {"symbol": sym, "spot": spot, "support": ind["support"], "resistance": ind["resistance"], "vwap": ind["vwap"], "ema20": ind["ema20"], "ema50": ind["ema50"], "rsi": ind["rsi"], "expected": expected, "sl": sl, "risk": risk, "t1": t1, "t2": t2, "rr": rr, "kelly": kelly, "action": action, "bullish": bullish, "pcr": pcr, "gamma_flip": gamma_flip, "max_pain": max_pain, "call_wall": call_wall, "put_wall": put_wall, "trend": "BULLISH" if bullish else "BEARISH", "day_open": ind["day_open"], "orb_h": ind["orb_h"], "orb_l": ind["orb_l"]}

def calc_otr(spot, day_open, orb_h, orb_l, vwap, vix=13):
    score = 0; reasons=[]
    if spot < day_open:
        score+=1; reasons.append("Spot Day Open se neeche")
    if spot < vwap:
        score+=1; reasons.append("Spot VWAP se neeche")
    if spot < orb_l:
        score+=1; reasons.append("Spot ORB Low se neeche - breakdown")
    if vix>18:
        score+=1; reasons.append(f"VIX high {vix}")
    verdict = "LOW RISK" if score<=1 else ("MEDIUM" if score==2 else "HIGH - CE BLOCK")
    return {"otr": float(score), "verdict": verdict, "reasons": reasons, "ce_blocked": score>=3}

# Paper portfolio
if "paper_cash" not in st.session_state:
    st.session_state.paper_cash = 500000.0
if "paper_pos" not in st.session_state:
    st.session_state.paper_pos = {}
if "paper_journal" not in st.session_state:
    st.session_state.paper_journal = []
if "last_setups" not in st.session_state:
    st.session_state.last_setups = {}

# Sidebar - lightweight
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    sym = st.selectbox("Index", list(INDEX_META.keys()), index=2)
    tf = st.selectbox("Timeframe", list(TF_MAP.keys()), index=1)
    lite = st.toggle("⚡ LITE MODE", value=True, help="ON = chain/Gemini skip, sirf spot+S/R+GEX lite. OFF = full chain bhi lao")
    auto_chain = st.toggle("Chain + GEX lao?", value=False, help="Chain thoda slow hai, jab chahiye tab ON karo")
    if st.button("🔄 REFRESH ALL"):
        st.cache_data.clear()
        st.rerun()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Trade Setup", "🔍 Scan All Indices", "📊 GEX + PCR", "🚨 OTR", "🏢 Equity", "💼 Paper Trade"])

with tab1:
    st.markdown(f"### Trade Setup - {sym} | {TF_MAP[tf]['label']}")
    if st.session_state.last_setups.get(sym):
        s = st.session_state.last_setups[sym]
        st.caption(f"Cached • ₹{s['spot']:,.2f}")
    col1, col2 = st.columns([1,3])
    with col1:
        do_scan = st.button(f"🚀 SCAN {sym}", type="primary", use_container_width=True)
    with col2:
        st.caption("Load pe auto-scan nahi hota. Button dabao tabhi 1-2 API call jayegi.")
    if do_scan:
        t0=time.time()
        with st.spinner("Spot + candles la raha hoon..."):
            sr = fetch_spot(sym)
            spot = sr["price"]
            if not spot:
                st.error("Spot nahi aaya. Network check karke dobara try karo. Trade mat lena.")
                st.stop()
            candles = fetch_candles(sym, tf)
            ind = calc_indicators(candles, spot)
            chain = fetch_chain_lite(sym) if (auto_chain or not lite) else None
            setup = calc_setup(sym, spot, ind, chain)
            st.session_state.last_setups[sym]=setup
        st.success(f"✅ {int((time.time()-t0)*1000)}ms • {sr['source']} • {len(candles)} candles • Chain: {chain['source'] if chain else 'SKIPPED (Lite)'}")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Spot Entry", f"₹{setup['spot']:,.2f}", delta=setup['trend'])
        c2.metric("Stop Loss", f"₹{setup['sl']:,.2f}", delta=f"Risk {setup['risk']:.1f}")
        c3.metric("Target 1", f"₹{setup['t1']:,.2f}")
        c4.metric("Risk/Reward", f"1:{setup['rr']:.2f}", delta=f"Kelly {setup['kelly']}%")
        c5,c6,c7,c8 = st.columns(4)
        c5.metric("Target 2", f"₹{setup['t2']:,.2f}")
        c6.metric("Support", f"₹{setup['support']:,.2f}")
        c7.metric("Resistance", f"₹{setup['resistance']:,.2f}")
        c8.metric("VWAP", f"₹{setup['vwap']:,.2f}", delta=f"RSI {setup['rsi']:.1f}")
        if setup['rr']<0.3:
            st.error("🛑 RR <0.3 - INVALID SETUP, WAIT. Entry/SL mix lag raha hai.")
        elif setup['trend']=="BEARISH":
            st.warning(f"Action: {setup['action']} • SL ke upar close ho to exit.")
        else:
            st.info(f"Action: {setup['action']} SPOT • Entry ₹{setup['spot']:,.2f} • SL ₹{setup['sl']:,.2f} • T1 ₹{setup['t1']:,.2f} • T2 ₹{setup['t2']:,.2f}")
        if setup['pcr'] is not None:
            st.caption(f"PCR {setup['pcr']} • Max Pain {setup['max_pain']:,.0f} • Call Wall {setup['call_wall']:,.0f} • Put Wall {setup['put_wall']:,.0f} • Expected Move ±{setup['expected']}")
        # Paper trade button isi setup se
        if st.button(f"📝 PAPER TRADE 1 LOT ({INDEX_META[sym]['lot']} qty) - {sym}", key=f"paper_{sym}"):
            lot = INDEX_META[sym]['lot']
            tid = f"{sym}_{int(time.time())}"
            st.session_state.paper_pos[tid] = {"id": tid, "symbol": sym, "action": setup['action'], "entry": setup['spot'], "sl": setup['sl'], "t1": setup['t1'], "t2": setup['t2'], "qty": lot, "time": dt.now(IST).strftime("%H:%M:%S")}
            st.success(f"Paper position liya: {sym} @ ₹{setup['spot']:,.2f}")
            st.rerun()
    else:
        if sym not in st.session_state.last_setups:
            st.info("👆 SCAN daba. Pehle se kuch load nahi hoga, isliye instant khulta hai.")

with tab2:
    st.markdown("### 🔍 Scan All Indices - 1-1 karke (Sequential, Safe)")
    st.caption("Parallel scan Streamlit me SessionInfo error deta tha, isliye sequential hai. Slow network pe bhi safe.")
    if st.button("🚀 SCAN ALL (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX)", type="primary", use_container_width=True):
        prog = st.progress(0)
        results=[]
        syms = list(INDEX_META.keys())
        for idx, s2 in enumerate(syms):
            prog.progress(int((idx+1)/len(syms)*100))
            try:
                sr = fetch_spot(s2)
                if not sr["price"]:
                    continue
                candles = fetch_candles(s2, tf)
                ind = calc_indicators(candles, sr["price"])
                setup = calc_setup(s2, sr["price"], ind, None)
                st.session_state.last_setups[s2]=setup
                results.append(setup)
            except Exception as e:
                st.caption(f"{s2} fail: {str(e)[:40]}")
        prog.progress(100)
        if results:
            for s in results:
                c1,c2,c3,c4 = st.columns(4)
                c1.metric(f"{s['symbol']} Entry", f"₹{s['spot']:,.2f}", delta=s['trend'])
                c2.metric("SL", f"₹{s['sl']:,.2f}")
                c3.metric("T1", f"₹{s['t1']:,.2f}")
                c4.metric("RR", f"1:{s['rr']:.2f}")
        else:
            st.error("Koi index load nahi hua - network check karo.")

with tab3:
    st.markdown("### 📊 GEX + PCR + Max Pain")
    st.caption("Chain tab khologe tabhi chain load hoga. Load pe nahi.")
    if st.button(f"Load Chain - {sym}"):
        with st.spinner("Chain la raha hoon (proxy, 4 sec max)..."):
            ch = fetch_chain_lite(sym)
            sr = fetch_spot(sym)
            if sr["price"]:
                candles = fetch_candles(sym, tf)
                ind = calc_indicators(candles, sr["price"])
                setup = calc_setup(sym, sr["price"], ind, ch)
                st.session_state.last_setups[sym]=setup
                if ch.get("rows"):
                    c1,c2,c3,c4 = st.columns(4)
                    c1.metric("PCR", f"{setup['pcr']}" if setup['pcr'] else "N/A")
                    c2.metric("Max Pain", f"{setup['max_pain']:,.0f}")
                    c3.metric("Call Wall", f"{setup['call_wall']:,.0f}")
                    c4.metric("Put Wall", f"{setup['put_wall']:,.0f}")
                    c5,c6 = st.columns(2)
                    c5.metric("Expected Move", f"±{setup['expected']}")
                    c6.metric("Gamma Flip / ATM", f"{setup['gamma_flip']:,.0f}")
                    if setup['spot'] and setup['gamma_flip']:
                        if setup['spot'] < setup['gamma_flip']:
                            st.warning(f"GEX Trap: Spot {setup['spot']:,.0f} < Flip {setup['gamma_flip']:,.0f} - Negative gamma zone")
                        else:
                            st.success(f"Spot {setup['spot']:,.0f} > Flip {setup['gamma_flip']:,.0f} - Positive gamma")
                    st.caption(f"Expiry: {ch.get('expiry','')} • Rows: {len(ch['rows'])} • Source: {ch['source']}")
                else:
                    st.warning(f"Chain empty - {ch['source']}. ATR mode se Expected Move ±{setup['expected']} use kar raha hoon.")
            else:
                st.error("Spot nahi aaya.")

with tab4:
    st.markdown("### 🚨 OTR - Opening Trap Radar")
    st.caption("OTR tab khologe tabhi calculate hoga.")
    if st.button("Calculate OTR"):
        sr = fetch_spot(sym)
        if sr["price"]:
            candles = fetch_candles(sym, tf)
            ind = calc_indicators(candles, sr["price"])
            otr = calc_otr(sr["price"], ind["day_open"], ind["orb_h"], ind["orb_l"], ind["vwap"], vix=13)
            c1,c2 = st.columns(2)
            c1.metric("OTR Score", f"{otr['otr']}")
            c2.metric("Verdict", otr['verdict'])
            for r in otr['reasons']:
                st.write(f"- {r}")
            if otr['ce_blocked']:
                st.error("🛑 CE BLOCK - CE mat lo, PE / WAIT dekho")
            else:
                st.success("✅ CE allowed")
        else:
            st.error("Spot nahi aaya.")

with tab5:
    st.markdown("### 🏢 Equity - Koi bhi NSE stock")
    eq = st.text_input("Stock symbol (NSE, bina .NS ke)", value="RELIANCE", key="eq_sym")
    if st.button("Scan Equity"):
        try:
            ysym = f"{eq.strip().upper()}.NS"
            j = _http_json(f"https://query2.finance.yahoo.com/v8/finance/chart/{ysym}?interval=15m&range=5d", timeout=3)
            res = j["chart"]["result"][0]
            meta = res["meta"]
            spot = float(meta.get("regularMarketPrice") or 0)
            q = res["indicators"]["quote"][0]
            candles=[]
            for i in range(len(res.get("timestamp", []))):
                try:
                    c = q["close"][i]
                    if c is None:
                        continue
                    candles.append({"o": float(q["open"][i] or c), "h": float(q["high"][i] or c), "l": float(q["low"][i] or c), "c": float(c), "v": float(q["volume"][i] or 0)})
                except Exception:
                    continue
            ind = calc_indicators(candles, spot)
            # Equity setup - same calc, lot 1
            setup = calc_setup(eq.upper(), spot, ind, None)
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Price", f"₹{spot:,.2f}", delta=setup['trend'])
            c2.metric("SL", f"₹{setup['sl']:,.2f}")
            c3.metric("T1", f"₹{setup['t1']:,.2f}")
            c4.metric("RR", f"1:{setup['rr']:.2f}")
            st.info(f"{eq.upper()} • VWAP ₹{ind['vwap']:,.2f} • RSI {ind['rsi']:.1f} • Support ₹{ind['support']:,.2f} • Resistance ₹{ind['resistance']:,.2f}")
        except Exception as e:
            st.error(f"Equity load fail: {str(e)[:60]}")

with tab6:
    st.markdown("### 💼 Paper Portfolio")
    st.metric("Cash", f"₹{st.session_state.paper_cash:,.2f}")
    if not st.session_state.paper_pos:
        st.info("Koi open position nahi.")
    else:
        for tid, pos in list(st.session_state.paper_pos.items()):
            c1,c2,c3,c4 = st.columns(4)
            c1.write(f"**{pos['symbol']}** {pos['action']} @ ₹{pos['entry']:,.2f}")
            c2.metric("SL", f"₹{pos['sl']:,.2f}")
            c3.metric("T1", f"₹{pos['t1']:,.2f}")
            c4.metric("Qty", f"{pos['qty']}")
            if st.button(f"Square Off {tid}", key=f"sq_{tid}"):
                # mock exit at entry +2% for demo, real me live price se hota
                exit_p = pos['entry']*1.01
                pnl = (exit_p-pos['entry'])*pos['qty'] if pos['action']=="BUY" else (pos['entry']-exit_p)*pos['qty']
                st.session_state.paper_cash += pnl
                st.session_state.paper_journal.append({"symbol": pos['symbol'], "entry": pos['entry'], "exit": exit_p, "pnl": round(pnl,2)})
                del st.session_state.paper_pos[tid]
                st.success(f"Closed, PnL ₹{pnl:,.2f}")
                st.rerun()
    if st.session_state.paper_journal:
        st.markdown("**Journal**")
        for j in st.session_state.paper_journal[-10:]:
            st.caption(f"{j['symbol']} Entry ₹{j['entry']:,.2f} → Exit ₹{j['exit']:,.2f} • PnL ₹{j['pnl']:,.2f}")

st.divider()
st.caption("Full features • Paper only • Real order disabled • FINNIFTY: NIFTY_FIN_SERVICE.NS • Range guard ON • SL sanity 3% ON")
