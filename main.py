import os
import requests
import numpy as np
import time
from datetime import datetime
from flask import Flask
from threading import Thread
import telebot

# Read the token from environment variables
TOKEN = os.getenv('BOT_TOKEN')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def get_klines(symbol, interval='1d', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return []

def calculate_rsi(data, period=14):
    closes = np.array([float(x[4]) for x in data], dtype=float)
    deltas = np.diff(closes)
    seed = deltas[:period]
    up = seed[seed > 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(closes)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(closes)):
        delta = deltas[i - 1]
        if delta > 0:
            up_val = delta
            down_val = 0.
        else:
            up_val = 0.
            down_val = -delta

        up = (up * (period - 1) + up_val) / period
        down = (down * (period - 1) + down_val) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)

    return round(rsi[-1], 2)

def calculate_ema(data, span):
    closes = np.array([float(x[4]) for x in data], dtype=float)
    return pd.Series(closes).ewm(span=span, adjust=False).mean().iloc[-1]

def analyze_symbol(symbol):
    klines = get_klines(symbol)
    
    if not klines or len(klines) == 0:
        return f"⚠️ Error: No data returned for {symbol.upper()}"

    try:
        current_price = float(klines[-1][4])
        rsi = calculate_rsi(klines)
        ema50 = calculate_ema(klines, 50)
        ema200 = calculate_ema(klines, 200)

        if ema50 > ema200:
            ema_trend = "📈 Uptrend"
        else:
            ema_trend = "📉 Downtrend"

        if current_price > ema50:
            ema_signal = "✅ Above EMA50"
        else:
            ema_signal = "⚠️ Below EMA50"

        candle_open = float(klines[-1][1])
        candle_close = float(klines[-1][4])

        if candle_close > candle_open:
            candle = "🟢 Bullish Candle"
        else:
            candle = "🔴 Bearish Candle"

        recommendation = "✅ Buy" if (rsi < 30 and ema50 > ema200) else "⚠️ Wait"

        return (
            f"💰 Price: ${round(current_price, 3)}\n"
            f"📊 RSI(14): {rsi}\n"
            f"📈 EMA Trend: {ema_trend}\n"
            f"📍 EMA Signal: {ema_signal}\n"
            f"🕯️ Candle: {candle}\n"
            f"📌 Recommendation: {recommendation}"
        )
    except Exception as e:
        return f"⚠️ Error analyzing {symbol.upper()}: {str(e)}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Send me a crypto symbol (like BTC, ETH, DOT) and I'll analyze it for you!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip().lower()

    symbol_mapping = {
        'eth': ['ETHUSDT', 'ETHBTC'],
        'btc': ['BTCUSDT'],
        'dot': ['DOTUSDT'],
        'rsr': ['RSRUSDT'],
        # Add more mappings if you want
    }

    if text in symbol_mapping:
        responses = []
        for sym in symbol_mapping[text]:
            analysis = analyze_symbol(sym)
            responses.append(f"🔍 {sym} Analysis:\n{analysis}")
        reply = "\n\n".join(responses)
    else:
        reply = "⚠️ Invalid or unsupported symbol."

    bot.reply_to(message, reply)

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    print("Bot is polling...")
    bot.polling(non_stop=True)
