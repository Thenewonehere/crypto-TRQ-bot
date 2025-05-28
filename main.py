import os
import requests
import numpy as np
import time
from datetime import datetime
from flask import Flask
from threading import Thread
import telebot
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
CHAT_ID = '-1002400439132'

# Flask server to keep bot alive
app = Flask('')

@app.route('/')
def home():
    return "Bot is running."

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# === Market Functions ===

def get_klines(symbol, interval='1d', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    return response.json()

def calculate_rsi(closes, period=14):
    deltas = np.diff(closes)
    seed = deltas[:period]
    up = seed[seed > 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = [100. - 100. / (1. + rs)]
    for delta in deltas[period:]:
        upval = max(delta, 0)
        downval = -min(delta, 0)
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi.append(100. - 100. / (1. + rs))
    return round(rsi[-1], 2)

def calculate_ema(prices, period):
    return round(np.convolve(prices, np.ones(period)/period, mode='valid')[-1], 2)

def detect_candle_pattern(data):
    o1, h1, l1, c1 = [float(x) for x in data[-2][:4]]
    o2, h2, l2, c2 = [float(x) for x in data[-1][:4]]
    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)

    if c2 > o2 and o2 < c1 and c1 < o1 and body2 > body1:
        return "✅ Bullish Engulfing"
    if body2 < (h2 - l2) * 0.3 and (o2 - l2 > body2 * 2 or c2 - l2 > body2 * 2):
        return "✅ Hammer"
    return "🔷 No clear pattern"

# === Main Logic ===

symbols = [
    "BTCUSDT", "ETHUSDT", "DOTUSDT", "XRPUSDT", "ETHBTC",
    "CHZUSDT", "CHRUSDT", "RSRUSDT", "JASMYUSDT",
    "FILUSDT", "KSMUSDT", "KDAUSDT"
]

def check_market_and_alert():
    for symbol in symbols:
        try:
            data = get_klines(symbol, '1d', 100)
            closes = [float(k[4]) for k in data]
            current_price = closes[-1]
            rsi = calculate_rsi(closes)
            ema_50 = calculate_ema(closes, 50)
            ema_200 = calculate_ema(closes, 200)
            candle = detect_candle_pattern(data)

            ema_trend = "✅ Bullish" if ema_50 > ema_200 else "❌ Bearish"
            ema_signal = "✅ Golden Cross" if ema_50 > ema_200 else "❌ Death Cross"
            recommendation = "🟢 BUY" if rsi < 30 and ema_50 > ema_200 and "✅" in candle else "⚪ No Signal"

            if recommendation == "🟢 BUY":
                msg = f"""🚨 BUY SIGNAL DETECTED!

🔍 {symbol} [1D]
💲 Price: ${round(current_price, 3)}
📊 RSI: {rsi} (Oversold)
📈 EMA50 > EMA200 ✅ Golden Cross
🕯️ Candle Pattern: {candle}
📌 Recommendation: {recommendation}
"""
                bot.send_message(chat_id=CHAT_ID, text=msg)

        except Exception as e:
            print(f"Error with {symbol}: {e}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    symbol = message.text.strip().upper()
    responses = []

    if symbol == "ETH":
        requests_list = ["ETHUSDT", "ETHBTC"]
    else:
        if not symbol.endswith("USDT") and symbol != "ETHBTC":
            symbol += "USDT"
        requests_list = [symbol]

    for s in requests_list:
        try:
            data = get_klines(s, '1d', 100)
            closes = [float(k[4]) for k in data]
            current_price = closes[-1]
            rsi = calculate_rsi(closes)
            ema_50 = calculate_ema(closes, 50)
            ema_200 = calculate_ema(closes, 200)
            candle = detect_candle_pattern(data)

            ema_trend = "✅ Bullish" if ema_50 > ema_200 else "❌ Bearish"
            ema_signal = "✅ Golden Cross" if ema_50 > ema_200 else "❌ Death Cross"
            recommendation = "🟢 BUY" if rsi < 30 and ema_50 > ema_200 and "✅" in candle else "⚪ No Signal"

            msg = f"""🔍 {s} [1D]
💲 Price: ${round(current_price, 3)}
📊 RSI(14): {rsi}
📈 EMA Trend: {ema_trend}
🌐 EMA Signal: {ema_signal}
🕯️ Candle: {candle}
📌 Recommendation: {recommendation}
"""
            responses.append(msg)
        except Exception as e:
            responses.append(f"⚠️ Error getting data for {s}: {e}")

    for reply in responses:
        bot.reply_to(message, reply)

def auto_checker():
    while True:
        now = datetime.utcnow().strftime('%H:%M')
        if now == "00:10":
            check_market_and_alert()
            time.sleep(60)
        time.sleep(20)

# === Run bot ===
if __name__ == "__main__":
    keep_alive()
    Thread(target=auto_checker).start()
    bot.infinity_polling()
