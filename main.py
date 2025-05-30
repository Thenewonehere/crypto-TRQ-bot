import os
import requests
import time
import numpy as np
from datetime import datetime
from flask import Flask
from threading import Thread
import telebot

TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

# ====== Functions ======

def get_klines_bybit(symbol, interval='D', limit=200):
    url = f"https://api.bybit.com/v5/market/kline?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get('result', {}).get('list', [])
    else:
        return []

def get_price_coingecko(symbol_id):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol_id}&vs_currencies=usd"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get(symbol_id, {}).get('usd')
    return None

def analyze_klines(klines):
    closes = np.array([float(k[4]) for k in klines], dtype=np.float64)
    opens = np.array([float(k[1]) for k in klines], dtype=np.float64)
    
    current_price = closes
