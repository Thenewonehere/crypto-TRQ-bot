import os
import requests
import numpy as np
import schedule
import time
from flask import Flask
from threading import Thread
import telebot
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
CMC_API_KEY = os.getenv("CMC_API_KEY")
CHANNEL_ID = "@Crypto_TRQ_Bot"

bot = telebot.TeleBot(TOKEN)

# ====== Functions ======

def get_klines_twelvedata(symbol, interval='1day', outputsize=100):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TWELVE_DATA_API_KEY}"
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

def get_btc_dominance():
    url = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"
    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": CMC_API_KEY,
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        dominance = data['data']['btc_dominance']
        return dominance
    else:
        return None

def btc_dominance_recommendation(dominance):
    if dominance > 52:
        return "📈 الهيمنة مرتفعة — قد تفضل البيتكوين، احذر من ضعف العملات البديلة."
    elif dominance < 48:
        return "📉 الهيمنة منخفضة — فرصة لصعود العملات البديلة (Altseason محتمل)."
    else:
        return "⚖️ الهيمنة متوازنة — لا تفوق واضح للبيتكوين أو العملات البديلة."

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
        return "نجم هابط"
    if body < candle_range * 0.3 and lower_shadow > body * 2 and upper_shadow < body:
        return "مطرقة"
    if abs(opens[-1] - closes[-1]) <= (highs[-1] - lows[-1]) * 0.1:
        return "دوجي"
    if closes[-1] > opens[-1] and closes[-2] < opens[-2] and closes[-1] > opens[-2] and opens[-1] < closes[-2]:
        return "ابتلاع شرائي"
    if closes[-1] < opens[-1] and closes[-2] > opens[-2] and opens[-1] > closes[-2] and closes[-1] < opens[-2]:
        return "ابتلاع بيعي"
    return "نمط غير واضح"

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
        return "🟢 شراء قوي"
    elif score <= -2:
        return "🔴 بيع قوي"
    else:
        return "🟠 إشارة متضاربة"

def volatility_level(atr, price):
    ratio = (atr / price) * 100
    if ratio < 1.5:
        return "🔵 سوق مستقر — مخاطرة منخفضة"
    elif ratio < 3:
        return "🟡 تذبذب متوسط — مخاطرة متوسطة"
    else:
        return "🔴 تذبذب عالي — مخاطرة مرتفعة ⚠️"

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
    volatility = volatility_level(atr, current_price)

    return current_price, candle_pattern, final_recommendation, volatility

def daily_report():
    symbols = ["XRP/USD", "BTC/USD", "ETH/USD", "ETH/BTC", "DOT/USD", "RSR/USD", "JASMY/USD", "KDA/USD", "FIL/USD", "ARB/USD"]
    report = f"🗓️ تقرير التحليل الفني اليومي\n📅 التاريخ: {datetime.now().strftime('%Y-%m-%d')}\n\n"

    for symbol in symbols:
        try:
            klines = get_klines_twelvedata(symbol)
            if klines:
                price, candle_pattern, final_recommendation, volatility = analyze_klines(klines)

                report += (
                    f"---------------------------\n"
                    f"🔍 تحليل {symbol} [1D]\n"
                    f"💰 السعر الحالي: ${price:.2f}\n"
                    f"📌 التوصية النهائية: {final_recommendation}\n"
                    f"🕯️ نمط الشمعة: {candle_pattern}\n"
                    f"🌡️ {volatility}\n"
                    f"✅ الملخص: القرار يميل إلى {final_recommendation.split()[1]} مع {volatility.split('—')[1]}.\n"
                )
        except Exception as e:
            continue

    dominance = get_btc_dominance()
    dominance_recommendation = btc_dominance_recommendation(dominance)

    report += (
        f"---------------------------\n"
        f"📈 Bitcoin Dominance (BTC.D)\n"
        f"🔹 النسبة الحالية: {dominance:.2f}%\n"
        f"📊 التوصية: {dominance_recommendation}\n"
    )

    bot.send_message(CHANNEL_ID, report)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip().upper()

    if text == "ETH":
        symbols = ["ETH/USD", "ETH/BTC"]
    else:
        symbols = [f"{text}/USD"]

    for symbol in symbols:
        try:
            klines = get_klines_twelvedata(symbol)
            if klines:
                price, candle_pattern, final_recommendation, volatility = analyze_klines(klines)

                msg = (
                    f"🔍 تحليل {symbol} [1D]\n"
                    f"💰 السعر الحالي: ${price:.2f}\n"
                    f"📌 التوصية النهائية: {final_recommendation}\n"
                    f"🕯️ نمط الشمعة: {candle_pattern}\n"
                    f"🌡️ {volatility}\n"
                    f"✅ الملخص: بناءً على التحليل، القرار يميل إلى {final_recommendation.split()[1]} مع {volatility.split('—')[1]}."
                )
                bot.reply_to(message, msg)
        except Exception as e:
            bot.reply_to(message, f"⚠️ لا توجد بيانات متوفرة للرمز {symbol}.")

# ====== Start Bot ======

app = Flask(__name__)

@app.route('/')
def home():
    return "البوت يعمل بنجاح!"

def start_bot():
    bot.infinity_polling()

def scheduler():
    schedule.every().day.at("04:10").do(daily_report)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    Thread(target=start_bot).start()
    Thread(target=scheduler).start()
    app.run(host="0.0.0.0", port=8080)
