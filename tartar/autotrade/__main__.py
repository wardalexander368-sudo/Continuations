"""python -m tartar.autotrade run | status | halt REASON | resume [STRATEGY] [--root autotrade]"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .ledger import Ledger
from .runner import ROOT, run_once


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tartar.autotrade")
    ap.add_argument("cmd", choices=("run", "status", "halt", "resume"))
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "run":
        s = run_once(root)
        print(json.dumps({k: v for k, v in s.items()}, default=str))
        return 0
    if a.cmd == "status":
        print((root / "REPORT.md").read_text() if (root / "REPORT.md").exists() else "no report yet")
        return 0
    ledger = Ledger(root)
    now = time.time()
    if a.cmd == "halt":
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
