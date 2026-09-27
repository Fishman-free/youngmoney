"""Shared synthetic-market helpers for offline unit tests (no network)."""

import os

from bnbot.data import MS_PER_HOUR, MarketData

T0 = 1704067200000  # 2024-01-01 00:00 UTC, multiple of 4h and 8h


def kline_rows(times, closes, spread=1.0, step_ms=4 * MS_PER_HOUR):
    rows = []
    for t, c in zip(times, closes):
        rows.append({
            "open_time": t,
            "open": c,
            "high": c + spread,
            "low": c - spread,
            "close": c,
            "volume": 100.0,
            "close_time": t + step_ms - 1,
        })
    return rows


def make_market(symbol="TESTUSDT", closes4h=None, closes1d=None, funding=None):
    """Build a MarketData with 4h + 1d series starting at T0.

    funding: list of (offset_ms, rate) tuples added to the funding cache.
    """
    md = MarketData()
    if closes4h is not None:
        times = [T0 + i * 4 * MS_PER_HOUR for i in range(len(closes4h))]
        from bnbot.data import BarSeries
        md.klines[(symbol, "4h")] = BarSeries(symbol, "4h", kline_rows(times, closes4h))
    if closes1d is not None:
        times = [T0 + i * 24 * MS_PER_HOUR for i in range(len(closes1d))]
        from bnbot.data import BarSeries
        md.klines[(symbol, "1d")] = BarSeries(symbol, "1d", kline_rows(times, closes1d, step_ms=24 * MS_PER_HOUR))
    md.funding[symbol] = {
        "times": [T0 + off for off, _ in (funding or [])],
        "rates": [r for _, r in (funding or [])],
    }
    return md


def make_config(tmpdir, symbols=("TESTUSDT",), **overrides):
    """Minimal config dict mirroring config.json; risk/kill paths inside tmpdir."""
    cfg = {
        "capital": 10000.0,
        "target_vol": 0.20,
        "symbols": list(symbols),
        "data": {
            "start": "2024-01-01",
            "intervals": ["4h", "1d"],
            "data_dir": str(tmpdir),
        },
        "strategy": {
            "weight_trend": 0.5,
            "weight_mom": 0.3,
            "donchian_window": 48,
            "ema_fast": 20,
            "ema_slow": 50,
            "mom_lookback_days": 30,
            "mom_deadband": 0.0,
            "funding_ann_threshold": 0.05,
            "carry_weight": 0.10,
            "vol_lookback_days": 30,
            "max_vol_scale": 2.0,
            "rebalance_band": 0.05,
        },
        "risk": {
            "max_gross_leverage": 2.0,
            "max_symbol_weight": 0.35,
            "daily_loss_stop": 0.03,
            "drawdown_throttle": 0.15,
            "drawdown_halt": 0.25,
            "kill_switch_file": os.path.join(str(tmpdir), "KILL_SWITCH"),
        },
        "fees": {"taker_bps": 5.0, "slippage_bps": 2.0},
        "live": {
            "paper_interval_hours": 4,
            "state_file": os.path.join(str(tmpdir), "state", "portfolio.json"),
            "log_dir": os.path.join(str(tmpdir), "logs"),
        },
    }
    for k, v in overrides.items():
        cfg[k] = v
    return cfg
