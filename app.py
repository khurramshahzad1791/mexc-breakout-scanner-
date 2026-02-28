import ccxt
import pandas as pd
import pandas_ta as ta
import streamlit as st
import time
from datetime import datetime

st.set_page_config(page_title="MEXC Pro Breakout Scanner 2026", layout="wide")
st.title("🚀 MEXC Low-Cap Pro Breakout Scanner v3 (Fixed)")
st.markdown("**200 EMA + RSI + ADX + RVOL confluence** | Clean & Fast | No dead APIs")

# ====================== SETTINGS ======================
TIMEFRAME = st.sidebar.selectbox("Timeframe", ["1d", "4h"], index=0)
RVOL_THRESHOLD = st.sidebar.slider("Min RVOL", 2.0, 6.0, 2.8, step=0.1)
VOL_MIN = 100_000
VOL_MAX = 5_000_000
CANDLES = 200
st.sidebar.info("Low-cap USDT pairs • High confluence setups")

# ====================== FETCH & SCAN ======================
@st.cache_data(ttl=300)
def get_scanner_data():
    exchange = ccxt.mexc({'enableRateLimit': True})
    tickers = exchange.fetch_tickers()
    
    # Filter USDT spot pairs in volume range
    candidates = [
        s for s, t in tickers.items()
        if s.endswith('/USDT') and VOL_MIN <= t.get('quoteVolume', 0) <= VOL_MAX
    ]
    
    results = []
    progress = st.progress(0)
    total = min(len(candidates), 350)  # limit to avoid timeout
    
    for i, symbol in enumerate(candidates[:total]):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=CANDLES)
            if len(ohlcv) < 150:
                continue
                
            df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            
            # Indicators
            df['ema9']   = ta.ema(df['close'], length=9)
            df['ema20']  = ta.ema(df['close'], length=20)
            df['ema200'] = ta.ema(df['close'], length=200)
            df['rsi']    = ta.rsi(df['close'], length=14)
            df['atr']    = ta.atr(df['high'], df['low'], df['close'], length=14)
            df['adx']    = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
            df['rvol']   = df['volume'] / df['volume'].rolling(5).mean()
            
            latest = df.iloc[-1]
            
            # Swing levels (recent 35 candles excluding very last 5)
            res_30 = df['high'][-40:-5].max()
            sup_30 = df['low'][-40:-5].min()
            
            # Common conditions
            trend_up   = latest['close'] > latest['ema200']
            trend_down = latest['close'] < latest['ema200']
            rsi_long   = 35 < latest['rsi'] < 70
            rsi_short  = 30 < latest['rsi'] < 65
            adx_ok     = latest['adx'] > 20
            rvol_ok    = latest['rvol'] > RVOL_THRESHOLD
            
            # Retest logic
            near_ema = abs(latest['close'] - latest['ema9']) / latest['close'] < 0.025 or \
                       abs(latest['close'] - latest['ema20']) / latest['close'] < 0.025
            vol_spike = latest['volume'] > df['volume'].rolling(5).mean().iloc[-1] * 1.2
            
            # Long setup
            long_condition = (
                rvol_ok and
                latest['close'] > latest['ema9'] > latest['ema20'] and
                trend_up and rsi_long and adx_ok and
                (latest['close'] >= res_30 * 0.99 or
                 (any(df['close'].iloc[-8:-1] > res_30 * 0.99) and near_ema and vol_spike))
            )
            
            # Short setup
            short_condition = (
                rvol_ok and
                latest['close'] < latest['ema9'] < latest['ema20'] and
                trend_down and rsi_short and adx_ok and
                (latest['close'] <= sup_30 * 1.01 or
                 (any(df['close'].iloc[-8:-1] < sup_30 * 1.01) and near_ema and vol_spike))
            )
            
            if not (long_condition or short_condition):
                progress.progress((i+1)/total)
                continue
            
            # Trade levels (ATR based)
            entry = latest['close']
            atr = latest['atr']
            
            if long_condition:
                direction = "🔥 LONG"
                sl = max(latest['low'], latest['ema20'] - atr * 0.6)
                tp1 = entry + atr * 3.0
                tp2 = entry + atr * 6.5
                rr = round((tp1 - entry) / (entry - sl), 2)
            else:
                direction = "🔻 SHORT"
                sl = min(latest['high'], latest['ema20'] + atr * 0.6)
                tp1 = entry - atr * 3.0
                tp2 = entry - atr * 6.5
                rr = round((entry - tp1) / (sl - entry), 2)
            
            # Simple score (no sentiment needed)
            score = round(latest['rvol'] * (latest['adx'] / 20) * rr, 2)
            
            results.append({
                'Symbol': symbol,
                'Direction': direction,
                'Price': round(entry, 6),
                'RVOL': round(latest['rvol'], 2),
                'RSI': round(latest['rsi'], 1),
                'ADX': round(latest['adx'], 1),
                'Entry': round(entry, 6),
                'SL': round(sl, 6),
                'TP1': round(tp1, 6),
                'TP2': round(tp2, 6),
                'RR': rr,
                'Score': score,
                'Volume24h': f"${tickers[symbol]['quoteVolume']:,.0f}"
            })
            
            progress.progress((i+1)/total)
            time.sleep(0.08)
            
        except Exception as e:
            continue  # silent skip
    
    return pd.DataFrame(results)

# ====================== DISPLAY ======================
if st.button("🔄 Run Scanner Now (2-4 min)"):
    with st.spinner("Scanning low-cap USDT pairs..."):
        data = get_scanner_data()
    
    if data.empty:
        st.warning("No strong setups found right now. Try again in 10-15 min or change timeframe.")
    else:
        st.success(f"Last Updated: {datetime.now().strftime('%I:%M %p PKT')}")
        
        long = data[data['Direction'].str.contains("LONG")].nlargest(10, 'Score')
        short = data[data['Direction'].str.contains("SHORT")].nlargest(10, 'Score')
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🔥 TOP 10 LONG")
            st.dataframe(long, use_container_width=True, hide_index=True)
        with col2:
            st.subheader("🔻 TOP 10 SHORT")
            st.dataframe(short, use_container_width=True, hide_index=True)
        
        csv = pd.concat([long, short]).to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "mexc_scanner_setups.csv")

st.caption("Fixed for Streamlit Cloud • Use $5 isolated • 20-50x leverage only • Made for khurram")
