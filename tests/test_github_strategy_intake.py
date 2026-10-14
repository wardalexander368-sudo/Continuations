import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
module_spec=importlib.util.spec_from_file_location("github_intake_tested", ROOT/"handoff/experiments/github_strategy_intake.py")
intake=importlib.util.module_from_spec(module_spec)
sys.modules[module_spec.name]=intake
module_spec.loader.exec_module(intake)


@pytest.fixture
def setup(tmp_path):
    cache=tmp_path/"cache";sources=tmp_path/"sources";cache.mkdir();sources.mkdir()
    (cache/"BTC.json").write_text(json.dumps({str(i):[p,1] for i,p in enumerate([100,120,80,90])}))
    (sources/"source.txt").write_text("Synthetic source contract fixture, not a profit or licensing claim")
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    spec={"schema_version":1,"candidate_id":"fixture", "source":{"repo_url":"https://github.com/example/fixture","commit":"a"*40,"files":[{"path":"source.txt","sha256":digest(sources/"source.txt")}],"license_spdx":"MIT","license_file":"source.txt","license_sha256":digest(sources/"source.txt")},"review":{"reviewer":"fixture","transcription_checked":True,"license_checked":True,"closed_lane_checked":True,"mechanism_note":"Synthetic adapter contract test only"},"method":{"adapter":"constant_weight_rebalance","weights":{"BTC":0.5},"interval_bars":1,"drift_band":0},"protocol":{"capital_usd":1000,"side_cost_bps":39,"stress_side_cost_bps":78,"start_hour":0,"end_hour":3,"evidence_class":"explored-history","planned_at":"2020-01-01T00:00:00Z"}}
    path=tmp_path/"spec.json";path.write_text(json.dumps(spec));return tmp_path/"state",path,cache,sources,spec


def run(setup):
    state,path,cache,sources,_=setup
    return intake.screen(state,path,cache,sources)


def test_identical_screen_is_reused_without_new_attempt(setup):
    first=run(setup);second=run(setup)
    assert first["status"] in {"REVIEW_ONLY","FAIL_SCREEN"}
    assert second["status"]=="SKIPPED_IDENTICAL_SCREEN"
    assert second["reused_attempt_id"]==first["attempt_id"]
    rows=intake.read_log(setup[0]);assert sum(r["kind"]=="started" for r in rows)==1
    assert all(r.get("validated_profitability",False) is False for r in rows)


def test_changed_origin_and_plan_timestamp_are_not_new_evidence(setup):
    first=run(setup);state,path,cache,sources,spec=setup
    spec["source"]["repo_url"]="https://github.com/another/fork"
    spec["source"]["commit"]="b"*40;spec["protocol"]["planned_at"]="2021-01-01T00:00:00Z"
    del spec["method"]["drift_band"]
    path.write_text(json.dumps(spec));second=run(setup)
    assert second["status"]=="SKIPPED_IDENTICAL_SCREEN" and second["reused_attempt_id"]==first["attempt_id"]
    assert intake.read_log(state)[-1]["origin"]["commit"]=="b"*40


def test_changed_unused_cache_hours_do_not_trigger_new_screen(setup):
    run(setup);p=setup[2]/"BTC.json";data=json.loads(p.read_text());data["4"]=[999,1];p.write_text(json.dumps(data))
    assert run(setup)["status"]=="SKIPPED_IDENTICAL_SCREEN"


def test_different_interpreter_identity_cannot_reuse_unchecked_old_receipt(setup,monkeypatch):
    monkeypatch.setattr(intake,"runtime_identity",lambda:{"python":"fixture-v1"})
    first=run(setup)
    monkeypatch.setattr(intake,"runtime_identity",lambda:{"python":"fixture-v2"})
    second=run(setup)
    assert second["status"] in {"REVIEW_ONLY","FAIL_SCREEN"}
    assert second["attempt_id"]!=first["attempt_id"]
    starts=[r for r in intake.read_log(setup[0]) if r["kind"]=="started"]
    assert starts[0]["method_identity"]==starts[1]["method_identity"]
    assert starts[0]["own_code"]["runtime"]!=starts[1]["own_code"]["runtime"]


def test_daily_budget_counts_distinct_attempts(setup):
    assert run(setup)["status"] in {"REVIEW_ONLY","FAIL_SCREEN"}
    state,path,_,_,spec=setup;spec["method"]["interval_bars"]=2;path.write_text(json.dumps(spec))
    assert run(setup)["status"] in {"REVIEW_ONLY","FAIL_SCREEN"}
    spec["method"]["weights"]["BTC"]=0.4;path.write_text(json.dumps(spec))
    assert run(setup)["status"]=="SKIPPED_DAILY_SCREEN_BUDGET"
    assert sum(r["kind"]=="started" for r in intake.read_log(state))==2


def test_corrupted_log_fails_closed_without_overwrite(setup):
    run(setup);p=setup[0]/"screen-log.jsonl";raw=p.read_bytes();p.write_bytes(raw.replace(b'"schema_version":1',b'"schema_version":9',1))
    damaged=p.read_bytes()
    with pytest.raises(ValueError,match="corrupt"):
        run(setup)
    assert p.read_bytes()==damaged


def test_completed_attempt_recovery_does_not_repeat_simulation(setup):
    first=run(setup);p=setup[0]/"screen-log.jsonl";p.write_bytes(p.read_bytes().splitlines(keepends=True)[0])
    second=run(setup)
    assert second["status"]=="SKIPPED_IDENTICAL_SCREEN" and second["reused_attempt_id"]==first["attempt_id"]
    rows=intake.read_log(setup[0]);assert rows[1]["recovered_completion"] is True
    assert len(list((setup[0]/"screens").iterdir()))==1


def test_missing_prior_result_is_explicit_not_valid_cached_evidence(setup):
    first=run(setup);(Path(first["output"])/"result.json").unlink()
    assert run(setup)["status"]=="PRIOR_RESULT_UNAVAILABLE"
    assert sum(r["kind"]=="started" for r in intake.read_log(setup[0]))==1


def test_invalid_review_retains_blocked_attempt(setup):
    state,path,_,_,spec=setup;spec["review"]["transcription_checked"]=False;path.write_text(json.dumps(spec))
    first=run(setup)
    assert first["status"]=="BLOCKED"
    assert json.loads((Path(first["output"])/"result.json").read_text())["error_code"]=="REVIEW_REQUIRED"
    assert run(setup)["status"]=="SKIPPED_IDENTICAL_SCREEN"


@pytest.mark.parametrize("suffix",["crypto-trading-system/x","autotrade/x","handoff/preregistration/x"])
def test_excluded_paths_rejected_before_directory_creation(tmp_path,suffix):
    target=tmp_path/suffix
    with pytest.raises(ValueError):intake.safe_root(target)
    assert not target.exists()


def test_symlink_result_directory_is_rejected_on_recovery(setup,tmp_path):
    first=run(setup);state=setup[0];p=state/"screen-log.jsonl";p.write_bytes(p.read_bytes().splitlines(keepends=True)[0])
    output=Path(first["output"]);moved=tmp_path/"moved";output.rename(moved);output.symlink_to(moved,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"):
        run(setup)
