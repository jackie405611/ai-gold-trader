import requests

TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

def send_signal(signal):

    text = f"""
XAUUSD SIGNAL

{signal['signal']}

Entry: {signal['entry']}
TP: {signal['tp']}
SL: {signal['sl']}

Confidence: {signal['confidence']}%
"""

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text
    })
