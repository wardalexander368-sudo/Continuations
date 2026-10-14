"""Run only synthetic CDE execution fixtures: no real windows, imports of X, or HTTP."""
import runpy
import sys
import time
import types
from pathlib import Path

import httpx
import pytest

SCORER = Path(__file__).resolve().parents[1] / "handoff/experiments/edge-hunt/perps/cde_forward.py"


def synthetic_environment(monkeypatch, tmp_path, *, final=True, fetch=False):
    args = [str(SCORER), str(tmp_path / "cache")]
    if final:
        args.append("--final")
    if not fetch:
        args.append("--no-fetch")
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    x = types.ModuleType("xs_coinbase")
    x.sig_vmom = object()
    x.run = lambda *args: [("2026-10-12", 0.01), ("2026-10-19", 0.02)]
    monkeypatch.setitem(sys.modules, "xs_coinbase", x)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(time, "time", lambda: 1546387200)  # Jan 2 2019: one synthetic fetch page per coin


@pytest.mark.parametrize("final", [True, False])
def test_final_flag_survives_local_module_argv_rewrite(monkeypatch, tmp_path, capsys, final):
    synthetic_environment(monkeypatch, tmp_path, final=final)
    runpy.run_path(str(SCORER), run_name="__main__")
    output = capsys.readouterr().out
    assert ("SUCCESS" in output) is final
    assert "after 20 bp/side" in output


@pytest.mark.parametrize("status", [503, 204])
def test_exhausted_http_retries_raise_instead_of_scoring(monkeypatch, tmp_path, capsys, status):
    synthetic_environment(monkeypatch, tmp_path, fetch=True)
    calls = []

    class BadClient:
        def __init__(self, **kwargs):
            pass

        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(status, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "Client", BadClient)
    with pytest.raises(httpx.HTTPStatusError if status == 503 else RuntimeError):
        runpy.run_path(str(SCORER), run_name="__main__")
    assert len(calls) == 5
    assert "SUCCESS" not in capsys.readouterr().out
    assert not (tmp_path / "cache/BTC.csv").exists()


def test_404_remains_unavailable_with_explicit_unknown_coverage(monkeypatch, tmp_path, capsys):
    synthetic_environment(monkeypatch, tmp_path, fetch=True)

    class MissingClient:
        def __init__(self, **kwargs):
            pass

        def get(self, url, **kwargs):
            return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "Client", MissingClient)
    runpy.run_path(str(SCORER), run_name="__main__")
    output = capsys.readouterr().out
    assert "HTTP 404; coverage unknown" in output
    assert len(list((tmp_path / "cache").glob("*.csv"))) == 23
