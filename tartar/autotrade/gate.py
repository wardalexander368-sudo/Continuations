"""The live gate: the one place that decides whether anything may be signed and sent with real keys.

Every live sender (the Solana spot senders in ``execution.py``, the Hyperliquid sender in
``hl_exchange.py``) calls ``require_live`` right before it signs, and the broker uses the same checks to
pick routes. Live needs all of:

* config ``mode`` == ``"live"`` (the committed config is ``dry_live``; flipping it is the user's call);
* config ``live_approved_on`` set to a date AND the environment variable ``TARTAR_LIVE_APPROVED`` equal to
  it (the user's standing approval, held as a secret, so a config edit alone can't go live);
* the sender's keys present in the environment;
* no kill switch: ``HALT`` or ``HALT_LIVE`` in the agent's root, or ``TARTAR_LIVE_KILL`` set.

Hyperliquid's testnet (``network: "testnet"``) goes through the same gate: the CI test sets mode
``live`` and a matching approval in a scratch root, with a throwaway testnet key, so the gate itself is
exercised end to end.
"""

from __future__ import annotations

import os
from pathlib import Path


class LiveNotAllowed(RuntimeError):
    pass


def approval_reason(config: dict, env=None) -> str | None:
    """Why the config and environment don't allow live trading, or None if they do."""
    env = os.environ if env is None else env
    if config.get("mode") != "live":
        return f"mode is {config.get('mode', 'paper')!r}, not 'live'"
    approved = config.get("live_approved_on")
    if not approved or env.get("TARTAR_LIVE_APPROVED") != approved:
        return "live trading is not approved (config live_approved_on and TARTAR_LIVE_APPROVED must match)"
    return None


def missing_keys(keys, env=None) -> list[str]:
    env = os.environ if env is None else env
    return [k for k in keys if not env.get(k)]


def kill_reason(root=None, env=None) -> str | None:
    """A kill switch that is on, or None."""
    env = os.environ if env is None else env
    root = Path(root) if root else None
    if root and (root / "HALT").exists():
        return "kill switch: HALT"
    if root and (root / "HALT_LIVE").exists():
        return "live kill switch: " + ((root / "HALT_LIVE").read_text().strip() or "HALT_LIVE file present")
    if env.get("TARTAR_LIVE_KILL"):
        return "live kill switch: TARTAR_LIVE_KILL is set"
    return None


def live_reason(config: dict, env=None, keys=(), root=None) -> str | None:
    why = approval_reason(config, env)
    if why:
        return why
    miss = missing_keys(keys, env)
    if miss:
        return "missing " + ", ".join(miss)
    return kill_reason(root, env)


def require_live(config: dict, env=None, keys=(), root=None) -> None:
    """Raise LiveNotAllowed unless everything above holds. Call it right before signing."""
    why = live_reason(config, env, keys, root)
    if why:
        raise LiveNotAllowed(why)
