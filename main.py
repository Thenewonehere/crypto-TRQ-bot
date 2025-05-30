import os
import requests
import numpy as np
from flask import Flask
from threading import Thread
import telebot

TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

# ====== Functions ======

def get_klines_bybit(symbol, interval='D', limit=100):
    url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json().get('result', {}).get('list', [])
        if not data:
            # Try smaller limit if empty
            url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={symbol}&interval={interval}&limit=50"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json().get('result', {}).get('list', [])
        return data
    else:
        return []

def calculate_rsi(closes, period=14):
    deltas = np.diff(closes)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(closes)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(closes)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period

        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)

    return rsi[-1]

def detect_candle_pattern(opens, highs, lows, closes):
    body = abs(closes[-1] - opens[-1])
    candle_range = highs[-1] - lows[-1]
    upper_shadow = highs[-1] - max(opens[-1], closes[-1])
    lower_shadow = min(opens[-1], closes[-1]) - lows[-1]

    if body < candle_range * 0.3 and upper_shadow > body * 2 and lower_shadow < body:
        return "Shooting Star"
    if body < candle_range * 0.3 and lower_shadow > body * 2 and upper_shadow < body:
        return "Hammer"
    if abs(opens[-1] - closes[-1]) <= (highs[-1] - lows[-1]) * 0.1:
        return "Doji"
    if closes[-1] > opens[-1] and closes[-2] < opens[-2] and closes[-1] > opens[-2] and opens[-1] < closes[-2]:
        return "Bullish Engulfing"
    if closes[-1] < opens[-1] and closes[-2] > opens[-2] and opens[-1] > closes[-2] and closes[-1] < opens[-2]:
        return "Bearish Engulfing"
    return "No clear pattern"

def analyze_klines(klines):
    closes = np.array([float(k[4]) for k in klines], dtype=np.float64)
    opens = np.array([float(k[1]) for k in klines], dtype=np.float64)
    highs = np.array([float(k[2]) for k in klines], dtype=np.float64)
    lows = np.array([float(k[3]) for k in klines], dtype=np.float64)

    current_price = closes[-1]
    ema50 = np.mean(closes[-50:])
    ema200 = np.mean(closes[-200:])

    ema_trend = "✅ Bullish" if ema50 > ema200 else "🚨 Bearish"
    ema_signal = "✅ Golden Cross" if ema50 > ema200 else "🔻 Death Cross"

    rsi = calculate_rsi(closes)
    candle_pattern = detect_candle_pattern(opens, highs, lows, closes)

    rsi_signal = "🟢 Buy Signal" if rsi < 30 else ("🔴 Sell Signal" if rsi > 70 else "⚪ No Signal")
    ema_cross_signal = "🟢 Buy Signal" if ema50 > ema200 else "🔴 Sell Signal"

    return current_price, rsi, ema_trend, ema_signal, candle_pattern, rsi_signal, ema_cross_signal

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    symbol = message.text.strip().upper()

    if symbol == "ETH":
        symbols = ["ETHUSDT", "ETHBTC"]
    else:
        symbols = [f"{symbol}USDT"]

    for sym in symbols:
        try:
            klines = get_klines_bybit(sym)
            if klines:
                price, rsi, ema_trend, ema_signal, candle_pattern, rsi_signal, ema_cross_signal = analyze_klines(klines)

                msg = (
                    f"\ud83d\udd0d {sym} [1D]\n"
                    f"\ud83d\udcb0 Price: ${price:.2f}\n"
                    f"\ud83d\udcca RSI(14): {rsi:.2f}\n"
                    f"\ud83d\udcc8 EMA Trend: {ema_trend}\n"
                    f"\ud83e\udeb9 EMA Signal: {ema_signal}\n"
                    f"\ud83d\udd2f Candle: {candle_pattern}\n"
                    f"\ud83d\udccc Recommendation:\n{rsi_signal}\n{ema_cross_signal}"
                )
            else:
                msg = f"⚠️ No data available for {sym}"

        except Exception as e:
            msg = f"⚠️ Error fetching {sym}: {str(e)}"

        bot.reply_to(message, msg)

# ====== Start Bot ======

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def start_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    Thread(target=start_bot).start()
    app.run(host="0.0.0.0", port=8080)
