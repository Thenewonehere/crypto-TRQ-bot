import os
import requests
import numpy as np
from flask import Flask
from threading import Thread
import telebot

TOKEN = os.getenv("BOT_TOKEN")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
CMC_API_KEY = os.getenv("CMC_API_KEY")

bot = telebot.TeleBot(TOKEN)

# ====== Functions ======

def get_klines_twelvedata(symbol, interval='1day', outputsize=100):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}/USD&interval={interval}&outputsize={outputsize}&apikey={TWELVE_DATA_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if 'values' in data:
            klines = []
            for item in reversed(data['values']):
                kline = [
                    item['datetime'],
                    float(item['open']),
                    float(item['high']),
                    float(item['low']),
                    float(item['close'])
                ]
                klines.append(kline)
            return klines
    return []

def get_price_coinmarketcap(symbol):
    url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={symbol}&convert=USD"
    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": CMC_API_KEY,
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        price = data['data'][symbol]['quote']['USD']['price']
        return price
    else:
        return None

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

def calculate_macd(closes, slow=26, fast=12, signal=9):
    ema_fast = np.convolve(closes, np.ones(fast)/fast, mode='valid')
    ema_slow = np.convolve(closes, np.ones(slow)/slow, mode='valid')
    macd_line = ema_fast[-len(ema_slow):] - ema_slow
    signal_line = np.convolve(macd_line, np.ones(signal)/signal, mode='valid')
    macd_hist = macd_line[-len(signal_line):] - signal_line
    return macd_hist[-1]

def calculate_stochastic_rsi(closes, period=14):
    rsi_series = []
    for i in range(period, len(closes)):
        window = closes[i - period:i]
        rsi = calculate_rsi(window, period)
        rsi_series.append(rsi)
    lowest_rsi = min(rsi_series)
    highest_rsi = max(rsi_series)
    current_rsi = rsi_series[-1]
    stochastic_rsi = (current_rsi - lowest_rsi) / (highest_rsi - lowest_rsi) * 100
    return stochastic_rsi

def calculate_atr(highs, lows, closes, period=14):
    tr = np.maximum(highs[1:], closes[:-1]) - np.minimum(lows[1:], closes[:-1])
    atr = np.mean(tr[-period:])
    return atr

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

def generate_final_recommendation(rsi, macd, stochastic_rsi):
    score = 0

    if rsi < 30:
        score += 1
    elif rsi > 70:
        score -= 1

    if macd > 0:
        score += 1
    else:
        score -= 1

    if stochastic_rsi < 20:
        score += 1
    elif stochastic_rsi > 80:
        score -= 1

    if score >= 2:
        return "🟢 Strong Buy"
    elif score <= -2:
        return "🔴 Strong Sell"
    else:
        return "🟠 Mixed Signal"

def analyze_klines(klines):
    closes = np.array([float(k[4]) for k in klines], dtype=np.float64)
    opens = np.array([float(k[1]) for k in klines], dtype=np.float64)
    highs = np.array([float(k[2]) for k in klines], dtype=np.float64)
    lows = np.array([float(k[3]) for k in klines], dtype=np.float64)

    current_price = closes[-1]

    rsi = calculate_rsi(closes)
    macd = calculate_macd(closes)
    stochastic_rsi = calculate_stochastic_rsi(closes)
    atr = calculate_atr(highs, lows, closes)
    candle_pattern = detect_candle_pattern(opens, highs, lows, closes)
    final_recommendation = generate_final_recommendation(rsi, macd, stochastic_rsi)

    return current_price, rsi, macd, stochastic_rsi, atr, candle_pattern, final_recommendation

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip().upper().split()
    symbol = text[0]
    interval = '1day'  # Default

    if len(text) > 1:
        interval = text[1]

    try:
        klines = get_klines_twelvedata(symbol, interval)
        if klines:
            price, rsi, macd, stochastic_rsi, atr, candle_pattern, final_recommendation = analyze_klines(klines)

            msg = (
                f"🔍 {symbol}/USD [{interval}]\n"
                f"💰 Price: ${price:.2f}\n"
                f"📊 RSI(14): {rsi:.2f}\n"
                f"📈 MACD: {macd:.2f}\n"
                f"📈 Stochastic RSI: {stochastic_rsi:.2f}%\n"
                f"📈 ATR: {atr:.2f}\n"
                f"🕯️ Candle: {candle_pattern}\n"
                f"📌 Recommendation: {final_recommendation}"
            )
        else:
            raise ValueError("No Klines from TwelveData")

    except Exception as e:
        price = get_price_coinmarketcap(symbol)
        if price:
            msg = (
                f"🔍 {symbol}/USD\n"
                f"💰 Price: ${price:.2f}\n"
                f"⚠️ Limited data (Price only)"
            )
        else:
            msg = f"⚠️ No data available for {symbol}"

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
