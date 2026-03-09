import time
from signal_generator import generate_signal
from telegram_bot import send_signal

while True:

    signal = generate_signal()

    if signal:
        send_signal(signal)

    time.sleep(60)
