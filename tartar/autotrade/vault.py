"""Vault twins: a deposit in a Hyperliquid vault (HLP) mirroring a vault-holding paper strategy (``vault_hold``).

Intents with ``meta["venue"] == "hyperliquid_vault"`` and ``meta["vault"]`` get this twin. The paper book is
unchanged; the twin deposits USDC from the trading account into the vault at the paper entry, is carried
across the paper strategy's interval closes (``meta["kept"]``: marked, nothing moves), and is withdrawn at a
final close. ``fills.jsonl`` rows: ``vault_deposit``, ``vault_roll_out`` / ``vault_roll_in``, ``vault_withdraw``,
each close with the comparison against its paper twin.

* **Pricing.** A follower's equity moves with the vault's time-weighted return. From one mark to the next,
  equity *= 1 + (pnl1 - pnl0) / accountValue0, read from the newest point of the vault's ``allTime`` history
  (``vaultDetails``; its PnL is cumulative, so marks from different fetches chain). HLP takes no commission
  and deposits and withdrawals have no fee, so the twin and the paper interval differ only by timing.
* ``dry`` (mode ``dry_live``): the deposit and withdrawal are checked against the vault's live state (open,
  accepting deposits, the minimum, the lockup, the vault's withdrawable funds) and booked at the live mark.
  Nothing is signed or sent; no account.
* ``live`` (mode ``live``, the gate's approval and ``HYPERLIQUID_AGENT_KEY`` + ``HYPERLIQUID_ACCOUNT``): a
  ``vaultTransfer`` L1 action signed with the agent key (``hl_exchange.HyperliquidExchange``), amounts in
  micro-USDC as in the official SDK. Every send re-checks the gate; deposits also stop on any kill switch,
  withdrawals don't. Equity and lockup are read back from ``vaultDetails`` with ``user`` =
  ``HYPERLIQUID_ACCOUNT`` (``followerState``). **Never used on mainnet.** API wallet: ``vaultTransfer`` is an L1
  action (signed like an order, ``sign_l1_action`` in the official SDK), not one of the user-signed actions
  that move funds out of the account (``usdSend``, ``withdraw3``, ``spotSend``, ``usdClassTransfer``,
  ``sendAsset``), so the agent key signs it for the account and no main key is needed; checked from the
  SDK and docs, not yet with funds (a failed first deposit is a failed leg, nothing else). The USDC must
  sit in the account's perp balance: the agent can't move spot USDC there (``usdClassTransfer`` is
  user-signed), and the deposit is refused before sending when ``withdrawable`` is short.

Restart safety: each deposit and withdrawal is written to ``vault_pending.json`` before it is sent. A
deposit or withdrawal left there by a run that died is never repeated blind: the broker compares the
account's vault equity with the book and adopts the transfer if it landed (live), or drops it (dry, where
nothing moved).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .safety import Pending

HL_INFO = "https://api.hyperliquid.xyz/info"
HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
DAY = 86400.0

VAULT_DEFAULTS = {
    "max_usd": 200.0,            # one twin's deposit (the registered paper size)
    "min_usd": 10.0,             # smaller deposits are skipped
    "budget_usd": 200.0,         # USD in open vault twins, all strategies together
    "max_trade_loss_pct": 0.10,  # a twin interval losing more halts that strategy's live entries
    "max_divergence_pct": 0.01,  # twin interval worse than its paper interval by more than this ...
    "divergence_streak": 3,      # ... this many in a row halts that strategy's live entries
    "max_signal_age_s": 3 * DAY, # a paper entry up to 3 days old is mirrored (vault history points are ~14 days apart)
    "lockup_days": {HLP: 4.0},   # Hyperliquid: HLP deposits lock 4 days, user vaults 1 day
    "default_lockup_days": 1.0,
    "dry_all": True,             # in dry_live, mirror every (non-shadow) vault strategy, promoted or not
}


def is_vault(meta: dict) -> bool:
    return meta.get("venue") == "hyperliquid_vault"


class VaultPending(Pending):
    """``vault_pending.json``: vault transfers sent or about to be sent (kept apart from the wallet reconcile's file)."""

    def __init__(self, root: Path | None):
        super().__init__(root)
        self.path = Path(root) / "vault_pending.json" if root else None


@dataclass
class Mark:
    t: float     # the vault point's time
    av: float    # vault account value there
    pnl: float   # vault cumulative PnL there

    def growth(self, later: "Mark") -> float:
        """The vault's time-weighted return from this mark to ``later``."""
        return (later.pnl - self.pnl) / self.av if self.av > 0 else 0.0


@dataclass
class VaultFill:
    route: str
    leg: str            # "deposit" | "withdraw"
    vault: str
    ok: bool
    usd: float = 0.0    # deposited or withdrawn
    mark: dict | None = None
    at: float = 0.0
    lockup_until: float | None = None
    error: str | None = None
    unknown: bool = False
    dry: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class VaultInfo:
    def __init__(self, url: str = HL_INFO, http=None, clock=time.time):
        self.url, self.http, self.clock = url, http, clock
        self._cache: dict[tuple, tuple[float, dict]] = {}

    def details(self, vault: str, user: str | None = None) -> dict:
        key = (vault, user)
        hit = self._cache.get(key)
        if hit and self.clock() - hit[0] < 60:
            return hit[1]
        import httpx

        http = self.http or httpx.Client(timeout=30)
        body = {"type": "vaultDetails", "vaultAddress": vault, **({"user": user} if user else {})}
        r = http.post(self.url, json=body)
        r.raise_for_status()
        d = r.json()
        if not isinstance(d, dict) or not d.get("portfolio"):
            raise RuntimeError(f"vaultDetails for {vault[:10]} has no portfolio")
        self._cache[key] = (self.clock(), d)
        return d


def mark_of(details: dict) -> Mark:
    port = dict((n, x) for n, x in details["portfolio"])["allTime"]
    t, av = port["accountValueHistory"][-1]
    t2, pnl = port["pnlHistory"][-1]
    return Mark(float(t) / 1000, float(av), float(pnl))


def lockup_days(cfg: dict, vault: str) -> float:
    return float((cfg.get("lockup_days") or {}).get(vault, cfg.get("default_lockup_days", 1.0)))


def deposit_problem(details: dict, usd: float, cfg: dict) -> str | None:
    if details.get("isClosed"):
        return "vault is closed"
    if details.get("allowDeposits") is False:
        return "vault does not accept deposits"
    if usd < cfg["min_usd"]:
        return f"${usd:.2f} under the ${cfg['min_usd']:.0f} minimum"
    return None


class DryVaultExecutor:
    """Checks each transfer against the vault's live state and books it at the live mark; sends nothing."""

    name = "dry"

    def __init__(self, cfg: dict | None = None, info: VaultInfo | None = None, clock=time.time):
        self.cfg = {**VAULT_DEFAULTS, **(cfg or {})}
        self.info, self.clock = info or VaultInfo(clock=clock), clock

    def mark(self, vault: str) -> Mark:
        return mark_of(self.info.details(vault))

    def held(self, vault: str) -> float | None:
        return None  # no account: nothing to reconcile

    def deposit(self, vault: str, usd: float) -> VaultFill:
        at = self.clock()
        try:
            d = self.info.details(vault)
            why = deposit_problem(d, usd, self.cfg)
            m = mark_of(d)
            if why:
                return VaultFill("dry", "deposit", vault, False, mark=asdict(m), at=at, error=why, dry=True)
            return VaultFill("dry", "deposit", vault, True, usd=usd, mark=asdict(m), at=at, dry=True,
                             lockup_until=at + lockup_days(self.cfg, vault) * DAY,
                             extra={"vault_apr": d.get("apr"), "leader_commission": d.get("leaderCommission")})
        except Exception as exc:  # noqa: BLE001 - a failed check is a failed leg
            return VaultFill("dry", "deposit", vault, False, at=at, error=f"{type(exc).__name__}: {exc}"[:300], dry=True)

    def withdraw(self, vault: str, usd: float, lockup_until: float | None = None) -> VaultFill:
        at = self.clock()
        try:
            if lockup_until and at < lockup_until:
                return VaultFill("dry", "withdraw", vault, False, at=at, dry=True, lockup_until=lockup_until,
                                 error=f"locked until {time.strftime('%Y-%m-%d %H:%M', time.gmtime(lockup_until))} UTC")
            d = self.info.details(vault)
            m = mark_of(d)
            free = d.get("maxDistributable")
            if free is not None and float(free) < usd:
                return VaultFill("dry", "withdraw", vault, False, mark=asdict(m), at=at, dry=True,
                                 error=f"vault can pay out ${float(free):.2f} < ${usd:.2f}")
            return VaultFill("dry", "withdraw", vault, True, usd=usd, mark=asdict(m), at=at, dry=True)
        except Exception as exc:  # noqa: BLE001
            return VaultFill("dry", "withdraw", vault, False, at=at, error=f"{type(exc).__name__}: {exc}"[:300], dry=True)


def micro_usd(usd: float) -> int:
    return int(usd * 1_000_000)


class LiveVaultExecutor:
    """``vaultTransfer`` actions signed with the agent key. ``guard(leg)`` re-checks the live gate right before each send."""

    name = "live"

    def __init__(self, exchange, account: str, cfg: dict | None = None, info: VaultInfo | None = None, guard=None, clock=time.time):
        self.ex, self.account = exchange, account
        self.cfg = {**VAULT_DEFAULTS, **(cfg or {})}
        self.info = info or VaultInfo(url=exchange.url + "/info", clock=clock)
        self.guard = guard or (lambda leg: None)
        self.clock = clock

    def mark(self, vault: str) -> Mark:
        return mark_of(self.info.details(vault))

    def follower(self, vault: str) -> dict:
        self.info._cache.pop((vault, self.account), None)  # always fresh: it decides what is held
        return self.info.details(vault, self.account).get("followerState") or {}

    def held(self, vault: str) -> float | None:
        return float(self.follower(vault).get("vaultEquity") or 0.0)

    def free_usd(self) -> float:
        """USDC the account could move out of its perp balance now (``clearinghouseState.withdrawable``)."""
        import httpx

        http = self.info.http or httpx.Client(timeout=30)
        r = http.post(self.info.url, json={"type": "clearinghouseState", "user": self.account})
        r.raise_for_status()
        return float((r.json() or {}).get("withdrawable") or 0.0)

    def _transfer(self, vault: str, deposit: bool, usd: float) -> dict:
        return self.ex.post({"type": "vaultTransfer", "vaultAddress": vault, "isDeposit": deposit, "usd": micro_usd(usd)})

    def deposit(self, vault: str, usd: float) -> VaultFill:
        at = self.clock()
        try:
            self.guard("open")
            d = self.info.details(vault)
            why = deposit_problem(d, usd, self.cfg)
            free = self.free_usd()
            if not why and free < usd:  # deposits come from the perp balance; the agent can't move spot USDC there
                why = f"only ${free:.2f} withdrawable in the account's perp balance < ${usd:.2f}"
            if why:
                return VaultFill("live", "deposit", vault, False, at=at, error=why)
            m = mark_of(d)
        except Exception as exc:  # noqa: BLE001 - nothing was sent
            return VaultFill("live", "deposit", vault, False, at=at, error=f"{type(exc).__name__}: {exc}"[:300])
        try:
            resp = self._transfer(vault, True, usd)
        except Exception as exc:  # noqa: BLE001 - it may have gone out
            return VaultFill("live", "deposit", vault, False, at=at, unknown=True, error=f"{type(exc).__name__}: {exc}"[:300])
        if resp.get("status") != "ok":
            return VaultFill("live", "deposit", vault, False, at=at, error=str(resp.get("response"))[:300])
        lock = None
        try:
            lock = float(self.follower(vault).get("lockupUntil") or 0) / 1000 or None
        except Exception:  # noqa: BLE001 - fall back to the schedule
            pass
        return VaultFill("live", "deposit", vault, True, usd=usd, mark=asdict(m), at=at,
                         lockup_until=lock or at + lockup_days(self.cfg, vault) * DAY, extra={"response": resp})

    def withdraw(self, vault: str, usd: float, lockup_until: float | None = None) -> VaultFill:
        """Withdraw ``usd`` (the twin's equity), capped at what the account holds in the vault."""
        at = self.clock()
        try:
            self.guard("close")
            fs = self.follower(vault)
            have = float(fs.get("vaultEquity") or 0.0)
            lock = float(fs.get("lockupUntil") or 0) / 1000
            if lock and at < lock:
                return VaultFill("live", "withdraw", vault, False, at=at, lockup_until=lock,
                                 error=f"locked until {time.strftime('%Y-%m-%d %H:%M', time.gmtime(lock))} UTC")
            amount = min(usd, have)
            if amount <= 0:
                return VaultFill("live", "withdraw", vault, False, at=at, error="no equity in the vault")
            m = mark_of(self.info.details(vault))
        except Exception as exc:  # noqa: BLE001 - nothing was sent
            return VaultFill("live", "withdraw", vault, False, at=at, error=f"{type(exc).__name__}: {exc}"[:300])
        try:
            resp = self._transfer(vault, False, amount)
        except Exception as exc:  # noqa: BLE001
            return VaultFill("live", "withdraw", vault, False, at=at, unknown=True, error=f"{type(exc).__name__}: {exc}"[:300])
        if resp.get("status") != "ok":
            return VaultFill("live", "withdraw", vault, False, at=at, error=str(resp.get("response"))[:300])
        return VaultFill("live", "withdraw", vault, True, usd=amount, mark=asdict(m), at=at, extra={"response": resp, "held_before": have})


def make_vault_executor(route: str, cfg: dict, env=None, config: dict | None = None, root=None, perps_cfg: dict | None = None):
    if route == "dry":
        return DryVaultExecutor(cfg)
    if route == "live":
        from .gate import require_live
        from .hl_exchange import PERP_KEYS, HyperliquidExchange

        config = config or {}
        require_live(config, env, PERP_KEYS)

        def guard(leg: str) -> None:  # deposits also honour the kill switches; withdrawals must still be able to exit
            require_live(config, env, PERP_KEYS, root if leg == "open" else None)

        ex = HyperliquidExchange(env["HYPERLIQUID_AGENT_KEY"], network=(perps_cfg or {}).get("network", "mainnet"))
        return LiveVaultExecutor(ex, env["HYPERLIQUID_ACCOUNT"], cfg, guard=guard)
    raise ValueError(f"unknown vault route {route!r}")
