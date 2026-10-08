"""Per-token feature state, shared by the live forecaster and the offline dataset builder.

The same code computes features in both places, so a model trained offline
sees exactly what it will see live. Features that a data source cannot provide
are NaN (gradient-boosted trees handle missing values natively).
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from ..candles import Candle
from .volatility import VolatilityEstimator, prior_sigma

NAN = float("nan")

# pump.fun tokens graduate to an AMM once roughly 85 SOL has been raised in the curve.
GRADUATION_SOL = 85.0

BASE_FEATURES = (
    # price action, in units of per-candle volatility
    "r1", "r2", "r3", "r1_raw", "mom5", "mom15",
    "log_sigma", "vol_ratio",
    "clv", "body", "range", "upper_wick", "lower_wick",
    "ema_dev", "ema_trend", "drawdown", "rise",
    # activity
    "log_volume", "volume_z", "log_trades", "trade_trend", "flat_streak", "idle",
    # order flow
    "count_imb", "flow_imb", "flow5", "whale_share",
    # wallets
    "log_traders", "new_trader_share", "cum_traders", "trader_growth",
    # creator (dev wallet)
    "creator_known", "creator_sell", "creator_sold", "creator_left",
    # lifecycle
    "age", "n_candles", "curve_progress", "log_price",
)  # fmt: skip

PARTIAL_FEATURES = (
    # the forming candle so far (all zero when predicting at its open)
    "f", "x0", "p_trades", "p_activity", "p_flow_imb", "p_range", "p_new_traders", "p_creator_sell", "p_idle",
)  # fmt: skip

from ..scam import RISK_FEATURES  # noqa: E402  (holder/scam behaviour, see tartar/scam.py)

FEATURES = BASE_FEATURES + PARTIAL_FEATURES + RISK_FEATURES


def _ratio(a: float, b: float) -> float:
    return (a - b) / (a + b) if a + b > 0 else 0.0


def _log_ema(logs: list[float], span: int) -> float:
    alpha = 2.0 / (span + 1.0)
    level = logs[0]
    for v in logs[1:]:
        level += alpha * (v - level)
    return level


class FeatureEngine:
    """Running state of one token, updated with each closed candle."""

    def __init__(
        self,
        timeframe: int,
        launched_at: float | None = None,
        creator_known: bool = False,
        window: int = 64,
        domain: str = "ohlcv",
    ):
        self.timeframe = timeframe
        self.launched_at = launched_at
        self.creator_known = creator_known
        self.vol = VolatilityEstimator(prior_sigma(timeframe, domain))
        self.fast_vol = VolatilityEstimator(prior_sigma(timeframe, domain), halflife=4.0)
        self.history: deque[Candle] = deque(maxlen=window)
        self.count = 0
        self.ath = 0.0
        self.atl = math.inf
        self.flat_streak = 0
        self.last_trade: float | None = None
        self.cum_traders = 0
        self.creator_bought = 0.0
        self.creator_sold = 0.0
        self.liquidity = 0.0
        self._base: np.ndarray | None = None
        self._avg_trades = 0.0

    @property
    def sigma(self) -> float:
        return self.vol.sigma

    def update(self, candle: Candle) -> None:
        prev = self.history[-1].close if self.history else None
        self.vol.update(prev, candle)
        self.fast_vol.update(prev, candle)
        self.history.append(candle)
        self.count += 1
        if candle.active:
            self.ath = max(self.ath, candle.high)
            self.atl = min(self.atl, candle.low)
            self.flat_streak = 0
            self.last_trade = candle.last_trade or float(candle.start + self.timeframe)
        else:
            self.flat_streak += 1
        self.cum_traders += candle.new_traders
        self.creator_bought += candle.creator_buy
        self.creator_sold += candle.creator_sell
        if candle.liquidity:
            self.liquidity = candle.liquidity
        self._base = None

    def features(self, partial: Candle | None = None, now: float | None = None, risk: dict[str, float] | None = None) -> np.ndarray:
        """Feature vector for predicting the close of the candle after the last closed one.

        `partial` is that candle as formed so far (None = predicting at its open);
        `risk` is the token's WalletTracker snapshot at that moment.
        """
        risk_values = np.array([(risk or {}).get(name, NAN) for name in RISK_FEATURES], dtype=float)
        if not self.creator_known:
            risk_values[RISK_FEATURES.index("creator_share")] = NAN
        return np.concatenate([self.base_features(), self._partial(partial, now), risk_values])

    def base_features(self) -> np.ndarray:
        if self._base is None:
            v = self._base_values()
            self._base = np.array([v.get(name, NAN) for name in BASE_FEATURES], dtype=float)
        return self._base

    def _base_values(self) -> dict[str, float]:
        h = self.history
        n = len(h)
        if n == 0:
            return {}
        tf = self.timeframe
        last = h[-1]
        sigma = self.sigma
        t_now = last.start + tf
        closes = [c.close for c in h]
        v: dict[str, float] = {}

        def log_ret(k: int, end: int = 0) -> float:
            i = n - 1 - end
            return math.log(closes[i] / closes[i - k]) if i - k >= 0 else NAN

        v["r1"], v["r2"], v["r3"] = (log_ret(1, e) / sigma for e in range(3))
        v["r1_raw"] = log_ret(1)
        v["mom5"] = log_ret(5) / (sigma * math.sqrt(5))
        v["mom15"] = log_ret(15) / (sigma * math.sqrt(15))
        v["log_sigma"] = math.log(sigma)
        v["vol_ratio"] = math.log(self.fast_vol.sigma / sigma)

        spread = last.high - last.low
        v["clv"] = ((last.close - last.low) - (last.high - last.close)) / spread if spread > 0 else 0.0
        v["body"] = math.log(last.close / last.open) / sigma
        v["range"] = math.log(last.high / last.low) / sigma
        v["upper_wick"] = math.log(last.high / max(last.open, last.close)) / sigma
        v["lower_wick"] = math.log(min(last.open, last.close) / last.low) / sigma
        if n >= 3:
            logs = [math.log(c) for c in closes]
            fast, slow = _log_ema(logs, 8), _log_ema(logs, 21)
            v["ema_dev"] = (logs[-1] - fast) / sigma
            v["ema_trend"] = (fast - slow) / sigma
        if self.ath > 0:
            v["drawdown"] = math.log(last.close / self.ath)
            v["rise"] = math.log(last.close / self.atl)

        v["log_volume"] = math.log1p(last.volume)
        # Compare volume only with candles from the same kind of source.
        same = [c.volume for c in h if (c.trades is None) == (last.trades is None)][-21:]
        if len(same) >= 4:
            logs_v = np.log1p(same)
            v["volume_z"] = float((logs_v[-1] - logs_v[:-1].mean()) / (logs_v[:-1].std() + 0.5))
        counted = [c.trades for c in list(h)[-11:-1] if c.trades is not None]
        self._avg_trades = float(np.mean(counted)) if counted else 0.0
        if last.trades is not None:
            v["log_trades"] = math.log1p(last.trades)
            v["trade_trend"] = math.log((1 + last.trades) / (1 + self._avg_trades)) if counted else NAN
            v["count_imb"] = _ratio(last.buys, last.sells)
            v["log_traders"] = math.log1p(last.traders)
            v["new_trader_share"] = last.new_traders / last.traders if last.traders else 0.0
        v["flat_streak"] = math.log1p(self.flat_streak)
        if self.last_trade is not None:
            v["idle"] = math.log1p(min(max(t_now - self.last_trade, 0.0) / tf, 1000.0))

        v["flow_imb"] = _ratio(last.buy_volume, last.sell_volume)
        recent = list(h)[-5:]
        v["flow5"] = _ratio(sum(c.buy_volume for c in recent), sum(c.sell_volume for c in recent))
        v["whale_share"] = last.max_trade / last.volume if last.volume > 0 else 0.0
        v["cum_traders"] = math.log1p(self.cum_traders)
        v["trader_growth"] = sum(c.new_traders for c in recent) / max(self.cum_traders, 1)

        v["creator_known"] = float(self.creator_known)
        if self.creator_known:
            v["creator_sell"] = math.log1p(last.creator_sell)
            v["creator_sold"] = math.log1p(self.creator_sold)
            if self.creator_bought > 0:
                v["creator_left"] = max(-1.0, 1.0 - self.creator_sold / self.creator_bought)

        if self.launched_at is not None:
            v["age"] = math.log1p(max(t_now - self.launched_at, 0.0) / 60.0)
        v["n_candles"] = math.log1p(self.count)
        if self.liquidity > 0:
            v["curve_progress"] = self.liquidity / GRADUATION_SOL
        v["log_price"] = math.log(last.close)
        return v

    def _partial(self, partial: Candle | None, now: float | None) -> np.ndarray:
        out = np.zeros(len(PARTIAL_FEATURES))
        if not self.history:
            out[:] = NAN
            return out
        self.base_features()  # refreshes the trade-rate average
        tf = self.timeframe
        last = self.history[-1]
        sigma = self.sigma
        t_open = last.start + tf
        if partial is None or now is None:
            now = float(t_open)
        f = min(max((now - t_open) / tf, 0.0), 1.0)
        last_trade = self.last_trade
        if partial is not None and partial.active:
            out[1] = math.log(partial.close / last.close) / sigma
            out[5] = math.log(partial.high / partial.low) / sigma
            if partial.last_trade:
                last_trade = partial.last_trade
        if partial is not None:
            if partial.trades is None:
                out[2] = out[3] = out[6] = NAN
            else:
                out[2] = math.log1p(partial.trades)
                out[3] = math.log((partial.trades + 1) / (f * self._avg_trades + 1))
                out[6] = math.log1p(partial.new_traders)
            out[4] = _ratio(partial.buy_volume, partial.sell_volume)
            out[7] = math.log1p(partial.creator_sell) if self.creator_known else NAN
        out[0] = f
        out[8] = math.log1p(min(max(now - last_trade, 0.0) / tf, 1000.0)) if last_trade is not None else NAN
        return out
