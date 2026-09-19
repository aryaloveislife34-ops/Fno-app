import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import json
import os

st.set_page_config(page_title="F&O Global Assistant", layout="wide", page_icon="🌍")
st.title("🌍 F&O Assistant — India + Global Markets")
st.caption("Nifty • Sensex • US • Asia • Europe")

LOG_FILE = "training_log.json"

def load_log():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_log(log):
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, default=str, indent=2)

@st.cache_data(ttl=60)
def get_data(symbol, period="5d", interval="5m"):
    tmap = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN"}
    df = yf.download(tmap.get(symbol, symbol + ".NS"), period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

@st.cache_data(ttl=300)
def get_vix():
    try:
        vix = yf.download("^INDIAVIX", period="5d", interval="1d", progress=False)['Close'].dropna()
        return float(vix.iloc[-1])
    except:
        return 14.0

@st.cache_data(ttl=300)
def get_global_market(ticker):
    """Global market ka latest data"""
    try:
        df = yf.download(ticker, period="5d", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        if len(df) < 2:
            return None
        current = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2])
        change = current - prev
        change_pct = (change / prev) * 100
        return {
            'price': current,
            'change': change,
            'change_pct': change_pct,
            'up': change > 0
        }
    except:
        return None

def add_indicators(df):
    df = df.copy()
    df['EMA20'] = df['Close'].ewm(span=20).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/loss))
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    df['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    df['VolMA'] = df['Volume'].rolling(20).mean()
    df['VWAP'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()
    return df

def hero_score(df, i):
    row = df.iloc[i]
    score = 0
    reasons = []
    if row['Close'] > row['VWAP']:
        score += 20; reasons.append("✅ VWAP ke upar")
    else:
        reasons.append("❌ VWAP ke neeche")
    if row['Volume'] > row['VolMA'] * 1.5:
        score += 20; reasons.append("✅ Volume high")
    elif row['Volume'] > row['VolMA'] * 1.2:
        score += 10; reasons.append("🟡 Volume thoda high")
    if i > 20:
        if row['Close'] > df['High'].iloc[max(0, i-20):i].max():
            score += 20; reasons.append("✅ Breakout upar")
        elif row['Close'] < df['Low'].iloc[max(0, i-20):i].min():
            score += 20; reasons.append("✅ Breakdown neeche")
    if i > 5:
        if row['Close'] > df['High'].iloc[max(0, i-5):i].max():
            score += 20; reasons.append("✅ Recent high break")
        elif row['Close'] < df['Low'].iloc[max(0, i-5):i].min():
            score += 20; reasons.append("✅ Recent low break")
    if i > 10:
        atr_avg = df['ATR'].iloc[max(0, i-10):i].mean()
        if row['ATR'] > atr_avg * 1.3:
            score += 20; reasons.append("✅ Volatility high")
        elif row['ATR'] > atr_avg * 1.1:
            score += 10; reasons.append("🟡 Volatility thodi high")
    return score, reasons

def analyze_index(symbol):
    df = get_data(symbol)
    if len(df) < 50:
        return None
    df = add_indicators(df)
    current = float(df['Close'].iloc[-1])
    score, reasons = hero_score(df, len(df)-1)
    vwap = float(df['VWAP'].iloc[-1])
    rsi = float(df['RSI'].iloc[-1])
    atr_v = float(df['ATR'].iloc[-1])
    
    direction = "BULLISH" if current > vwap else "BEARISH"
    trade = "BUY CE" if direction == "BULLISH" else "BUY PE"
    
    if trade == "BUY CE":
        entry = current
        sl = entry - atr_v * 1.5
        t1 = entry + atr_v * 2
        t2 = entry + atr_v * 3
    else:
        entry = current
        sl = entry + atr_v * 1.5
        t1 = entry - atr_v * 2
        t2 = entry - atr_v * 3
    
    profit_pct_t1 = abs(t1 - entry) / entry * 100
    profit_pct_t2 = abs(t2 - entry) / entry * 100
    loss_pct_sl = abs(entry - sl) / entry * 100
    
    return {
        'symbol': symbol, 'price': current, 'score': score,
        'trade': trade, 'direction': direction,
        'entry': entry, 'sl': sl, 't1': t1, 't2': t2,
        'profit_t1': profit_pct_t1, 'profit_t2': profit_pct_t2,
        'loss_sl': loss_pct_sl,
        'rsi': rsi, 'atr': atr_v, 'reasons': reasons,
        'df': df
    }

def make_chart(df, symbol, color='#2196F3'):
    df = df.tail(100).copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'], name='Price',
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ))
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA20',
                              line=dict(color=color, width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], name='VWAP',
                              line=dict(color='#FFD700', width=2, dash='dash')))
    fig.update_layout(
        title=f"{symbol}",
        template='plotly_dark',
        height=600,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=50, b=10),
        dragmode='pan',
        hovermode='x unified'
    )
    return fig

def get_global_sentiment():
    """Global markets ka overall sentiment"""
    markets = {
        'Dow Jones': '^DJI',
        'S&P 500': '^GSPC',
        'Nasdaq': '^IXIC',
        'Nikkei': '^N225',
        'Hang Seng': '^HSI',
        'FTSE': '^FTSE',
        'DAX': '^GDAXI'
    }
    
    results = {}
    up_count = 0
    down_count = 0
    
    for name, ticker in markets.items():
        data = get_global_market(ticker)
        if data:
            results[name] = data
            if data['up']:
                up_count += 1
            else:
                down_count += 1
    
    if up_count > down_count:
        sentiment = "BULLISH 🟢"
    elif down_count > up_count:
        sentiment = "BEARISH 🔴"
    else:
        sentiment = "MIXED 🟡"
    
    return results, sentiment, up_count, down_count

def voice_text(nifty, sensex, vix, global_sentiment):
    """Normal Hindi me samjhao"""
    if vix < 12:
        vix_msg = "Market abhi shaant hai"
    elif vix < 15:
        vix_msg = "Market normal hai"
    elif vix < 20:
        vix_msg = "Market thoda tez hai"
    else:
        vix_msg = "Market bahut tez hai"
    
    msg = f"Namaste. Market update suniye. "
    msg += f"Global market ka sentiment {global_sentiment} hai. "
    msg += f"India VIX {vix:.1f} — {vix_msg}. "
    
    if nifty:
        score = nifty['score']
        if nifty['trade'] == 'BUY CE':
            direction = "upar ja raha hai"; option = "Call option khareedo"
        else:
            direction = "neeche ja raha hai"; option = "Put option khareedo"
        
        if score >= 80: strength = "bahut strong"
        elif score >= 60: strength = "strong"
        else: strength = "thoda kamzor"
        
        msg += f"Nifty abhi {nifty['price']:.0f} pe hai. Market {direction}. "
        msg += f"Signal {strength} hai — {score} out of 100. "
        msg += f"Aap {nifty['entry']:.0f} pe {option}. "
        msg += f"Agar {nifty['t1']:.0f} tak gaya, to {nifty['profit_t1']:.1f} percent ka fayda. "
        msg += f"Agar {nifty['sl']:.0f} pe aa gaya, to {nifty['loss_sl']:.1f} percent ka nuksan. "
    
    if sensex:
        score = sensex['score']
        if sensex['trade'] == 'BUY CE':
            direction = "upar ja raha hai"; option = "Call option khareedo"
        else:
            direction = "neeche ja raha hai"; option = "Put option khareedo"
        
        if score >= 80: strength = "bahut strong"
        elif score >= 60: strength = "strong"
        else: strength = "thoda kamzor"
        
        msg += f"Sensex abhi {sensex['price']:.0f} pe hai. Market {direction}. "
        msg += f"Signal {strength} hai — {score} out of 100. "
        msg += f"Aap {sensex['entry']:.0f} pe {option}. "
        msg += f"Agar {sensex['t1']:.0f} tak gaya, to {sensex['profit_t1']:.1f} percent ka fayda. "
        msg += f"Agar {sensex['sl']:.0f} pe aa gaya, to {sensex['loss_sl']:.1f} percent ka nuksan. "
    
    if nifty and sensex:
        if nifty['trade'] == sensex['trade']:
            msg += f"Dono index ek hi direction me hain — signal strong hai. "
        else:
            msg += "Dono index alag alag direction me hain — market me confusion hai. Wait karo. "
    
    msg += "Yaad rakhiye — yeh sirf analysis hai. Guarantee nahi. Stop loss zaroor lagao."
    return msg

# ============ UI ============
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Live", "🌍 Global Markets", "🎙️ Voice", "📝 Training", "📈 Accuracy"])

with tab1:
    c1, c2 = st.columns([3, 1])
    with c2:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
    
    vix = get_vix()
    vix_color = "🟢" if vix < 15 else ("🟡" if vix < 20 else "🔴")
    st.markdown(f"### {vix_color} India VIX: **{vix:.2f}**")
    
    with st.spinner("Analyzing..."):
        nifty = analyze_index("NIFTY")
        sensex = analyze_index("SENSEX")
    
    if not nifty or not sensex:
        st.error("Data nahi mila. Refresh karo.")
    else:
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🔵 NIFTY")
            m1, m2, m3 = st.columns(3)
            m1.metric("Price", f"{nifty['price']:,.0f}")
            m2.metric("Score", f"{nifty['score']}/100")
            m3.metric("Signal", nifty['trade'])
            
            if nifty['trade'] == 'BUY CE':
                st.success(f"🟢 **{nifty['trade']}** — Kharidne ka mauka")
            else:
                st.error(f"🔴 **{nifty['trade']}** — Bechne ka mauka")
            
            st.write(f"**Entry:** {nifty['entry']:,.0f}")
            st.write(f"**Stop Loss:** {nifty['sl']:,.0f} ({nifty['loss_sl']:.1f}%)")
            st.write(f"**Target 1:** {nifty['t1']:,.0f} ({nifty['profit_t1']:.1f}%)")
            st.write(f"**Target 2:** {nifty['t2']:,.0f} ({nifty['profit_t2']:.1f}%)")
            
            st.plotly_chart(make_chart(nifty['df'], "NIFTY", '#2196F3'), use_container_width=True)
        
        with col2:
            st.markdown("### 🟠 SENSEX")
            m1, m2, m3 = st.columns(3)
            m1.metric("Price", f"{sensex['price']:,.0f}")
            m2.metric("Score", f"{sensex['score']}/100")
            m3.metric("Signal", sensex['trade'])
            
            if sensex['trade'] == 'BUY CE':
                st.success(f"🟢 **{sensex['trade']}** — Kharidne ka mauka")
            else:
                st.error(f"🔴 **{sensex['trade']}** — Bechne ka mauka")
            
            st.write(f"**Entry:** {sensex['entry']:,.0f}")
            st.write(f"**Stop Loss:** {sensex['sl']:,.0f} ({sensex['loss_sl']:.1f}%)")
            st.write(f"**Target 1:** {sensex['t1']:,.0f} ({sensex['profit_t1']:.1f}%)")
            st.write(f"**Target 2:** {sensex['t2']:,.0f} ({sensex['profit_t2']:.1f}%)")
            
            st.plotly_chart(make_chart(sensex['df'], "SENSEX", '#FF9800'), use_container_width=True)
        
        st.markdown("---")
        if nifty['trade'] == sensex['trade']:
            st.success(f"✅ **Dono {nifty['trade']} — Strong Signal!**")
        else:
            st.warning(f"⚠️ **Conflict** — WAIT karo")

with tab2:
    st.markdown("### 🌍 Global Markets — India Se Pehle Kya Ho Raha Hai")
    st.caption("US aur Asia market raat ko chalta hai — India ke opening ko affect karta hai")
    
    if st.button("🔄 Global Data Refresh"):
        st.cache_data.clear()
    
    with st.spinner("Global markets load kar raha hoon..."):
        results, sentiment, up_count, down_count = get_global_sentiment()
    
    st.markdown("---")
    st.markdown(f"## Global Sentiment: **{sentiment}**")
    st.write(f"**{up_count} markets upar** • **{down_count} markets neeche**")
    
    if "BULLISH" in sentiment:
        st.success("🟢 Global markets positive hain — Indian market bhi upar khulne ke chances zyada")
    elif "BEARISH" in sentiment:
        st.error("🔴 Global markets negative hain — Indian market gap-down khul sakta hai")
    else:
        st.warning("🟡 Mixed — koi clear direction nahi")
    
    st.markdown("---")
    
    # US Markets
    st.markdown("### 🇺🇸 US Markets (Raat ko chalta hai)")
    us_markets = ['Dow Jones', 'S&P 500', 'Nasdaq']
    cols = st.columns(3)
    for i, name in enumerate(us_markets):
        if name in results:
            data = results[name]
            with cols[i]:
                emoji = "🟢" if data['up'] else "🔴"
                st.metric(f"{emoji} {name}", f"{data['price']:,.0f}", 
                         f"{data['change_pct']:+.2f}%")
    
    st.markdown("### 🇯🇵🇭🇰 Asia Markets")
    asia_markets = ['Nikkei', 'Hang Seng']
    cols = st.columns(2)
    for i, name in enumerate(asia_markets):
        if name in results:
            data = results[name]
            with cols[i]:
                emoji = "🟢" if data['up'] else "🔴"
                st.metric(f"{emoji} {name}", f"{data['price']:,.0f}",
                         f"{data['change_pct']:+.2f}%")
    
    st.markdown("### 🇬🇧🇩🇪 Europe Markets")
    eu_markets = ['FTSE', 'DAX']
    cols = st.columns(2)
    for i, name in enumerate(eu_markets):
        if name in results:
            data = results[name]
            with cols[i]:
                emoji = "🟢" if data['up'] else "🔴"
                st.metric(f"{emoji} {name}", f"{data['price']:,.0f}",
                         f"{data['change_pct']:+.2f}%")
    
    st.markdown("---")
    st.info("💡 **Kaise use karo:** Agar US market raat ko strong upar close hua → subah Indian market bhi upar khulne ke chances zyada. Global sentiment ke saath apne signal ko confirm karo.")

with tab3:
    st.markdown("### 🎙️ Voice Assistant")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        voice_input = st.text_input("🎤 Bolo:", placeholder="Nifty aur Sensex kaisa hai?")
    with col2:
        st.write("")
        if st.button("🔊 Suno", use_container_width=True):
            vix = get_vix()
            with st.spinner("Analyzing..."):
                n = analyze_index("NIFTY")
                s = analyze_index("SENSEX")
                _, sentiment, _, _ = get_global_sentiment()
            msg = voice_text(n, s, vix, sentiment)
            st.success("📢 App bol raha hai:")
            st.write(msg)
            st.components.v1.html(f"""
            <script>
                const text = `{msg}`;
                const u = new SpeechSynthesisUtterance(text);
                u.lang = 'hi-IN'; u.rate = 0.85;
                speechSynthesis.speak(u);
            </script>
            """, height=0)
    
    if voice_input:
        vix = get_vix()
        with st.spinner("Analyzing..."):
            n = analyze_index("NIFTY")
            s = analyze_index("SENSEX")
            _, sentiment, _, _ = get_global_sentiment()
        msg = voice_text(n, s, vix, sentiment)
        st.markdown("---")
        st.markdown("### 🤖 App Ka Jawab")
        st.success(msg)
        st.components.v1.html(f"""
        <button onclick="speak()" style="
            background: #4CAF50; color: white; border: none;
            padding: 15px 30px; font-size: 16px; border-radius: 50px;
            cursor: pointer;
        ">🔊 Voice me Suno</button>
        <script>
        function speak() {{
            const text = `{msg}`;
            const u = new SpeechSynthesisUtterance(text);
            u.lang = 'hi-IN'; u.rate = 0.85;
            speechSynthesis.speak(u);
        }}
        </script>
        """, height=80)

with tab4:
    st.subheader("📝 Training Log")
    log = load_log()
    if not log:
        st.info("Live tab pe signals dekho aur log karo.")
    else:
        for i, entry in enumerate(log):
            with st.expander(f"#{i+1} — {entry['date']} — {entry['symbol']} {entry['trade']} — {entry['result']}"):
                result = st.radio("Result?", ["PENDING", "SAHI (Profit)", "GALAT (Loss)", "BREAKEVEN"],
                                 index=["PENDING", "SAHI (Profit)", "GALAT (Loss)", "BREAKEVEN"].index(entry['result']),
                                 key=f"r_{i}")
                if st.button("💾 Update", key=f"u_{i}"):
                    log[i]['result'] = result
                    save_log(log)
                    st.rerun()
        if st.button("🗑️ Clear All"):
            save_log([])
            st.rerun()

with tab5:
    st.subheader("📈 Accuracy Dashboard")
    log = load_log()
    if not log:
        st.info("Pehle signals log karo.")
    else:
        total = len(log)
        sahi = sum(1 for e in log if e['result'] == 'SAHI (Profit)')
        galat = sum(1 for e in log if e['result'] == 'GALAT (Loss)')
        pending = sum(1 for e in log if e['result'] == 'PENDING')
        completed = sahi + galat
        accuracy = (sahi / completed * 100) if completed > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", total)
        c2.metric("✅ Sahi", sahi)
        c3.metric("❌ Galat", galat)
        c4.metric("⏸️ Pending", pending)
        st.metric("🎯 Accuracy", f"{accuracy:.1f}%")

st.markdown("---")
st.caption(f"Updated: {datetime.now().strftime('%d-%b-%Y %H:%M')} | Educational only. Paper trade first.")
