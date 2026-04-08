from strategy_engine import analyze_market

def generate_signal():

    signal, price = analyze_market()

    if signal == "NEUTRAL":
        return None

    tp = 10
    sl = 7

    if signal == "BUY":
        entry = price
        take_profit = price + tp
        stop_loss = price - sl

    else:
        entry = price
        take_profit = price - tp
        stop_loss = price + sl

    confidence = 75

    return {
        "signal": signal,
        "entry": round(entry,2),
        "tp": round(take_profit,2),
        "sl": round(stop_loss,2),
        "confidence": confidence
    }
