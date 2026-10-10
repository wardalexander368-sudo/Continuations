"""python -m tartar.autotrade run | status | halt REASON | resume [STRATEGY] | halt-live REASON | resume-live [STRATEGY]
       | preflight | health | release-lease | dry-swap MINT [--sol 0.01] [--route lightning] | dry-perp COIN [--usd 12] [--side -1]   [--root autotrade]

halt-live stops new live twins (paper and exits keep running); preflight checks the live path without
trading; dry-swap builds a real Jupiter (or Lightning, via trade-local) buy and sell for MINT and has the RPC simulate them (no key, nothing sent);
dry-perp prices opening and closing a Hyperliquid perp twin on the live order book (no key, nothing sent)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .ledger import Ledger
from .runner import ROOT, run_once


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tartar.autotrade")
    ap.add_argument("cmd", choices=("run", "status", "halt", "resume", "halt-live", "resume-live", "preflight", "dry-swap", "dry-perp", "health", "release-lease"))
    ap.add_argument("--sol", type=float, default=0.01)
    ap.add_argument("--route", default="jupiter", choices=("jupiter", "lightning"))
    ap.add_argument("--usd", type=float, default=12.0)
    ap.add_argument("--side", type=int, default=1, choices=(1, -1))
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "run":
        from .safety import Busy, run_lock

        try:
            with run_lock(root):
                s = run_once(root)
        except Busy as exc:
            s = {"at": time.time(), "opened": 0, "closed": 0, "rejected": 0, "errors": {}, "changes": [], "halted": None,
                 "new_halts": [], "skipped": str(exc)}
        print(json.dumps({k: v for k, v in s.items()}, default=str))
        return 0
    if a.cmd == "release-lease":
        from .safety import holder_id, release_lease

        led = Ledger(root)
        if release_lease(led.state, holder_id()):
            led.save()
        return 0
    if a.cmd == "health":
        from .health import run as health

        h = health(root, Path("."))
        print(json.dumps(h, indent=1))
        return 1 if h["status"] == "red" else 0
    if a.cmd == "status":
        print((root / "REPORT.md").read_text() if (root / "REPORT.md").exists() else "no report yet")
        return 0
    ledger = Ledger(root)
    now = time.time()
    if a.cmd == "preflight":
        from .broker import preflight
        from .runner import load_config

        print(json.dumps(preflight(load_config(root), ledger, root), indent=1, default=str))
        return 0
    if a.cmd == "dry-swap":
        from .execution import JupiterExecutor, LightningExecutor

        ex = LightningExecutor(simulate=True) if a.route == "lightning" else JupiterExecutor(simulate=True)
        buy = ex.buy(a.arg, a.sol)
        sell = ex.sell(a.arg, buy.token_raw) if buy.ok else None
        print(json.dumps({"buy": buy.to_dict(), "sell": sell and sell.to_dict(),
                          "round_trip_pct": sell and 100 * (sell.sol / buy.sol - 1)}, indent=1, default=str))
        return 0 if buy.ok and sell and sell.ok else 1
    if a.cmd == "dry-perp":
        from .perps import DryPerpExecutor

        ex = DryPerpExecutor()
        o = ex.open(a.arg, a.side, a.usd)
        c = ex.close(a.arg, a.side, o.sz) if o.ok else None
        rt = c and 100 * (a.side * o.sz * (c.px - o.px) - o.fee_usd - c.fee_usd) / o.notional_usd
        print(json.dumps({"open": o.to_dict(), "close": c and c.to_dict(), "round_trip_pct": rt}, indent=1, default=str))
        return 0 if o.ok and c and c.ok else 1
    if a.cmd == "halt-live":
        (root / "HALT_LIVE").write_text(a.arg or "live halted by hand")
        ledger.change({"t": now, "kind": "halt", "scope": "live", "reason": a.arg or "live halted by hand"})
    elif a.cmd == "resume-live":
        live = ledger.state.setdefault("live", {})
        if a.arg:
            live.setdefault("strategies", {}).setdefault(a.arg, {}).update({"halted": None, "divergence_run": 0})
        else:
            (root / "HALT_LIVE").unlink(missing_ok=True)
            live["halted"] = None
        ledger.change({"t": now, "kind": "resume", "scope": f"live:{a.arg or 'all'}", "reason": "resumed by hand"})
    elif a.cmd == "halt":
        (root / "HALT").write_text(a.arg or "halted by hand")
        ledger.change({"t": now, "kind": "halt", "scope": "agent", "reason": a.arg or "halted by hand"})
    else:  # resume
        if a.arg:
            rec = ledger.strategy(a.arg)
            if rec["status"] == "halted":
                rec["status"] = rec.pop("status_before_halt", "paper")
            rec["errors"] = 0
            ledger.change({"t": now, "kind": "resume", "scope": a.arg, "reason": "resumed by hand"})
        else:
            (root / "HALT").unlink(missing_ok=True)
            ledger.state["halted"] = None
            ledger.change({"t": now, "kind": "resume", "scope": "agent", "reason": "resumed by hand"})
    ledger.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
