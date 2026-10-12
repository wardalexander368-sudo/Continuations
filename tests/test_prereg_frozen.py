"""Pre-registered tests are frozen (AGENTS.md rule 8, handoff/STATUS.md).

Every protocol file under handoff/preregistration/ that existed when this check was added is
pinned by SHA-256 in handoff/preregistration/FROZEN.sha256. Adding files (a dated ADDENDUM, a
RESULT, a new registration) is fine; changing or deleting a pinned file fails. Files the
collectors rewrite on purpose (dip cohorts, measured fees, auto results) are not pinned.

To pin a new registration once it is frozen:  python3 tests/test_prereg_frozen.py --pin
(that only adds files; it never re-pins a changed one).
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRE = ROOT / "handoff" / "preregistration"
PINS = PRE / "FROZEN.sha256"


def _unpinned(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (rel == "FROZEN.sha256" or name.startswith(("RESULT-auto-", "cohort-"))
            or rel == "dip-rolling/fees-measured.json")


def _digest(path: Path) -> str:
    # CRLF-normalized so a Windows checkout hashes the same as Linux/macOS
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _pins() -> dict:
    out = {}
    for line in PINS.read_text().splitlines():
        if line.strip():
            digest, rel = line.split("  ", 1)
            out[rel] = digest
    return out


def test_pinned_preregistrations_unchanged():
    changed, missing = [], []
    for rel, digest in _pins().items():
        path = PRE / rel
        if not path.exists():
            missing.append(rel)
        elif _digest(path) != digest:
            changed.append(rel)
    assert not missing, f"frozen preregistration files deleted: {missing}"
    assert not changed, (f"frozen preregistration files edited: {changed}. "
                         "Add a dated ADDENDUM file instead (AGENTS.md rule 8).")


def test_pins_cover_only_pinnable_files():
    assert not [rel for rel in _pins() if _unpinned(rel)]


if __name__ == "__main__" and sys.argv[1:] == ["--pin"]:
    pins = _pins() if PINS.exists() else {}
    for path in sorted(p for p in PRE.rglob("*") if p.is_file()):
        rel = path.relative_to(PRE).as_posix()
        if rel not in pins and not _unpinned(rel):
            pins[rel] = _digest(path)
            print("pinned", rel)
    PINS.write_text("".join(f"{d}  {r}\n" for r, d in sorted(pins.items())))
