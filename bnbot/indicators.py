"""Technical indicators (adopted from global-stock-data's indicator layer).

Pure-Python, zero-dependency implementations of the classics the skills bundle
ships: MA/EMA, MACD, RSI, KDJ, Bollinger Bands. Kept dependency-free so the
platform stays stdlib-only, and written to match the conventions the skill
documents so cross-checking against other tools agrees.

All functions take a list of floats (close prices unless noted) and return
either a list aligned to the input (None during warm-up) or a dict of lists.
"""


def sma(values, period):
    """Simple moving average; None until the window is full."""
    out, s = [None] * len(values), 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def ema(values, period):
    """Exponential moving average seeded with the first SMA (TA convention)."""
    out = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def macd(values, fast=12, slow=26, signal=9):
    """MACD line / signal / histogram (hist = dif - dea)."""
    ef, es = ema(values, fast), ema(values, slow)
    dif = [None if (ef[i] is None or es[i] is None) else ef[i] - es[i] for i in range(len(values))]
    idx = [i for i, v in enumerate(dif) if v is not None]
    dea = [None] * len(values)
    if idx:
        tail = [dif[i] for i in idx]
        sig = ema(tail, signal)
        for j, i in enumerate(idx):
            dea[i] = sig[j]
    hist = [None if (dif[i] is None or dea[i] is None) else dif[i] - dea[i] for i in range(len(values))]
    return {"dif": dif, "dea": dea, "hist": hist}


def rsi(values, period=14):
    """Wilder's RSI."""
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def kdj(highs, lows, closes, n=9, m1=3, m2=3):
    """KDJ: RSV over n bars, K/D smoothed, J = 3K - 2D."""
    k_list, d_list, j_list = [None] * len(closes), [None] * len(closes), [None] * len(closes)
    k = d = 50.0
    for i in range(len(closes)):
        if i < n - 1:
            continue
        hh = max(highs[i - n + 1:i + 1])
        ll = min(lows[i - n + 1:i + 1])
        rsv = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0
        k = (m1 - 1) / m1 * k + rsv / m1
        d = (m2 - 1) / m2 * d + k / m2
        k_list[i], d_list[i], j_list[i] = k, d, 3 * k - 2 * d
    return {"k": k_list, "d": d_list, "j": j_list}


def bollinger(values, period=20, mult=2.0):
    """Bollinger Bands: middle SMA +/- mult * population stddev."""
    mid = sma(values, period)
    up, low = [None] * len(values), [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        m = mid[i]
        var = sum((v - m) ** 2 for v in window) / period
        sd = var ** 0.5
        up[i], low[i] = m + mult * sd, m - mult * sd
    return {"mid": mid, "upper": up, "lower": low}


def atr(highs, lows, closes, period=14):
    """Average True Range (Wilder smoothing)."""
    n = len(closes)
    out = [None] * n
    if n <= period:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    prev = sum(trs[1:period + 1]) / period
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out
