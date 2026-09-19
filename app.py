import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="F&O Navigator", layout="wide", page_icon="🎯")
st.title("🎯 F&O Navigator")
st.caption("Entry • Target • Stop Loss • Confidence")

@st.cache_data(ttl=300)
def get_price_data(symbol, period="6mo", interval="1d"):
    ticker_map = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN"}
    ticker = ticker_map.get(symbol, symbol + ".NS")
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

def atr(df, period=14):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def find_sr(df, window=5, tol=0.003):
    highs, lows = df['High'].values, df['Low'].values
    res, sup = [], []
    for i in range(window, len(df) - window):
        if highs[i] == max(highs[i-window:i+window+1]):
            res.append(highs[i])
        if lows[i] == min(lows[i-window:i+window+1]):
            sup.append(lows[i])
    def cluster(levels):
        if not levels: return []
        levels = sorted(levels)
        out, cur = [], [levels[0]]
        for l in levels[1:]:
            if abs(l - cur[-1]) / cur[-1] < tol:
                cur.append(l)
            else:
                out.append(np.mean(cur)); cur = [l]
        out.append(np.mean(cur))
        return out
    return cluster(sup), cluster(res)

def expected_move(spot, iv_pct, days=1):
    return spot * (iv_pct / 100) * np.sqrt(days / 365)

def get_india_vix():
    try:
        vix = yf.download("^INDIAVIX", period="5d", progress=False)['Close'].dropna()
        return float(vix.iloc[-1])
    except:
        return 14.0

def generate_signal(symbol):
    df = get_price_data(symbol)
    if len(df) < 30:
        return None
    
    spot = float(df['Close'].iloc[-1])
    atr_val = float(atr(df).iloc[-1])
    sup, res = find_sr(df)
    
    nearest_sup = max([s for s in sup if s < spot], default=spot - atr_val*2)
    nearest_res = min([r for r in res if r > spot], default=spot + atr_val*2)
    
    ema20 = float(df['Close'].ewm(span=20).mean().iloc[-1])
    ema50 = float(df['Close'].ewm(span=50).mean().iloc[-1])
    
    iv = get_india_vix()
    exp_move = expected_move(spot, iv, days=1)
    
    if ema20 > ema50 and spot > nearest_sup:
        direction = "BUY"
        entry = spot
        sl = nearest_sup - atr_val * 0.5
        t1 = entry + (entry - sl) * 1.5
        t2 = entry + (entry - sl) * 2.5
        t3 = nearest_res
    elif ema20 < ema50 and spot < nearest_res:
        direction = "SELL"
        entry = spot
        sl = nearest_res + atr_val * 0.5
        t1 = entry - (sl - entry) * 1.5
        t2 = entry - (sl - entry) * 2.5
        t3 = nearest_sup
    else:
        return {
            'symbol': symbol, 'spot': round(spot, 2), 'signal': 'WAIT',
            'reason': 'No clear trend — market sideways', 'atr': round(atr_val, 2),
            'support': round(nearest_sup, 2), 'resistance': round(nearest_res, 2)
        }
    
    rr1 = abs(t1 - entry) / abs(entry - sl)
    rr2 = abs(t2 - entry) / abs(entry - sl)
    trend_strength = abs(ema20 - ema50) / spot * 100
    confidence = min(85, 50 + trend_strength * 200)
    
    return {
        'symbol': symbol, 'spot': round(spot, 2), 'signal': direction,
        'entry': round(entry, 2), 'stop_loss': round(sl, 2),
        'target1': round(t1, 2), 'target2': round(t2, 2), 'target3': round(t3, 2),
        'risk_reward_1': round(rr1, 2), 'risk_reward_2': round(rr2, 2),
        'atr': round(atr_val, 2), 'expected_move': round(exp_move, 2),
        'support': round(nearest_sup, 2), 'resistance': round(nearest_res, 2),
        'confidence': round(confidence, 1), 'iv': round(iv, 2)
    }

col_a, col_b = st.columns([2, 1])
with col_a:
    symbol = st.selectbox("Index/Stock chuno", ["NIFTY", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS", "HDFCBANK"])
with col_b:
    st.write("")
    st.write("")
    run = st.button("🚀 Signal Generate Karo", use_container_width=True)

if run:
    with st.spinner("Analyzing market data..."):
        result = generate_signal(symbol)
    
    if result is None:
        st.error("Data nahi mila. Internet check karo.")
    elif result['signal'] == 'WAIT':
        st.warning(f"⏸️ WAIT — {result['reason']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Spot", result['spot'])
        c2.metric("Support", result['support'])
        c3.metric("Resistance", result['resistance'])
    else:
        color = "🟢" if result['signal'] == "BUY" else "🔴"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Signal", f"{color} {result['signal']}")
        c2.metric("Confidence", f"{result['confidence']}%")
        c3.metric("Spot", result['spot'])
        c4.metric("India VIX", result['iv'])
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📍 Trade Levels")
            st.success(f"**Entry:** {result['entry']}")
            st.error(f"**Stop Loss:** {result['stop_loss']}")
            st.info(f"**Target 1:** {result['target1']}  (RR 1:{result['risk_reward_1']})")
            st.info(f"**Target 2:** {result['target2']}  (RR 1:{result['risk_reward_2']})")
            st.info(f"**Target 3:** {result['target3']}")
        with col2:
            st.subheader("📊 Market Context")
            st.write(f"**ATR (14-day):** {result['atr']}")
            st.write(f"**Expected Move (1 din):** ±{result['expected_move']} points")
            st.write(f"**Nearest Support:** {result['support']}")
            st.write(f"**Nearest Resistance:** {result['resistance']}")
        
        st.warning("⚠️ Yeh educational tool hai. Real paisa lagane se pehle paper trade karo.")

st.markdown("---")
st.caption(f"Last updated: {datetime.now().strftime('%d-%b-%Y %H:%M')} | Data: Yahoo Finance")
