import os
import time
import requests
import pandas as pd
import numpy as np

# ==========================
# 환경변수 불러오기
# ==========================
BINANCE_FUTURES_BASE = os.getenv("BINANCE_FUTURES_BASE", "https://fapi.binance.com")
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVALS = os.getenv("INTERVALS", "15m,1h").split(",")
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
PIVOT_LOOKBACK = int(os.getenv("PIVOT_LOOKBACK", "5"))
POLL_SEC = int(os.getenv("POLL_SEC", "60"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ==========================
# Binance API 호출
# ==========================
def fetch_klines(symbol, interval, limit=200):
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    df = pd.DataFrame(
        data,
        columns=[
            "time", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "_"
        ]
    )
    df["close"] = df["close"].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df[["time", "close"]]


# ==========================
# RSI 계산
# ==========================
def calc_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=period).mean()
    avg_loss = pd.Series(loss).rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ==========================
# 다이버전스 탐지
# ==========================
def detect_divergence(df, rsi_series):
    closes = df["close"].values
    rsis = rsi_series.values

    # 피벗 구하기
    pivots_price = []
    pivots_rsi = []
    for i in range(PIVOT_LOOKBACK, len(closes) - PIVOT_LOOKBACK):
        local_low = closes[i] == min(closes[i - PIVOT_LOOKBACK:i + PIVOT_LOOKBACK + 1])
        local_high = closes[i] == max(closes[i - PIVOT_LOOKBACK:i + PIVOT_LOOKBACK + 1])
        if local_low or local_high:
            pivots_price.append((i, closes[i]))
            pivots_rsi.append((i, rsis[i]))

    if len(pivots_price) < 2:
        return None

    (i1, p1), (i2, p2) = pivots_price[-2], pivots_price[-1]
    (j1, r1), (j2, r2) = pivots_rsi[-2], pivots_rsi[-1]

    # 불리시 다이버전스: 가격 하락, RSI 상승
    if p2 < p1 and r2 > r1:
        return "📈 Bullish Divergence"
    # 베어리시 다이버전스: 가격 상승, RSI 하락
    if p2 > p1 and r2 < r1:
        return "📉 Bearish Divergence"

    return None


# ==========================
# 텔레그램 알림
# ==========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정 없음, 메시지:", msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("텔레그램 전송 오류:", e)


# ==========================
# 메인 루프
# ==========================
if __name__ == "__main__":
    print(f"▶ RSI Divergence Bot 시작: {SYMBOL}, intervals={INTERVALS}")
    while True:
        try:
            for interval in INTERVALS:
                df = fetch_klines(SYMBOL, interval, 200)
                rsi = calc_rsi(df["close"], RSI_PERIOD)
                signal = detect_divergence(df, rsi)
                if signal:
                    msg = f"{signal} 감지됨\n종목: {SYMBOL}\n주기: {interval}\n시간: {df['time'].iloc[-1]}"
                    print(msg)
                    send_telegram(msg)
        except Exception as e:
            print("오류 발생:", e)
        time.sleep(POLL_SEC)