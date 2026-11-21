"""Runner, quality gates, publish, notificacoes e persistencia."""

import json
import urllib.request

import pytest

from conftest import CaptureNotifier
from db import connect
from quality import runner
from quality.context import CheckContext
from quality.models import CheckResult, worst
from quality.notifier import ConsoleNotifier, WebhookNotifier, build_payload, get_notifier
from quality.pipeline import run_pipeline
from quality.runner import REGISTRY, load_checks, run_quality_gate


# ----------------------------------------------------------------------------- config
def test_checks_are_configuration():
    specs = load_checks()
    assert {s["layer"] for s in specs} == {"bronze", "silver", "semantic"}
    assert all(s["type"] in REGISTRY and s.get("why") for s in specs)
    assert {"freshness", "schema_diff", "row_count", "null_rate", "duplicate_rows", "pagination_complete",
            "truncated_response"} <= {s["type"] for s in specs}


def test_unknown_check_type_is_rejected(tmp_path):
    bad = tmp_path / "c.yaml"
    bad.write_text("checks:\n  - {name: x, provider: all, layer: bronze, type: nope, dataset: d}\n")
    with pytest.raises(ValueError, match="unknown type"):
        load_checks(bad)


def test_severity_warning_caps_fail_at_warn():
    ctx = CheckContext("r", "voluum", "silver", silver_rows=[])
    r = CheckResult("r", ctx.checked_at, "voluum", "d", "silver", "c", "volume", "FAIL")
    out = runner._apply_spec_metadata({"name": "c", "type": "rolling_avg_change", "severity": "warning", "why": "w"}, r)
    assert out.status == "WARN" and out.details["capped_by_severity"] and out.details["why_it_matters"] == "w"
    r2 = CheckResult("r", ctx.checked_at, "voluum", "d", "silver", "c", "volume", "FAIL")
    assert runner._apply_spec_metadata({"name": "c", "type": "x", "severity": "critical"}, r2).status == "FAIL"


def test_a_check_that_cannot_run_is_a_fail_not_a_pass(monkeypatch):
    monkeypatch.setitem(REGISTRY, "freshness", lambda spec, ctx: 1 / 0)
    ctx = CheckContext("r", "voluum", "bronze")
    [result] = runner._run_one({"name": "boom", "type": "freshness", "dataset": "d"}, ctx)
    assert result.status == "FAIL" and "ZeroDivisionError" in result.details["error"]


def test_worst_status():
    assert worst(["PASS", "WARN"]) == "WARN" and worst(["PASS", "FAIL", "WARN"]) == "FAIL" and worst([]) == "PASS"


# ----------------------------------------------------------------------------- gates sobre dados reais
def one_spec(name):
    return [s for s in load_checks() if s["name"] == name]


def test_warn_does_not_block(broken_run):
    notifier = CaptureNotifier()
    gate = run_quality_gate("bronze", broken_run.run_id, provider="erobella", checks=one_spec("erobella_clicks_null_rate"),
                            persist=False, notifier=notifier)
    assert gate.status == "WARN" and gate.publish_allowed is True
    assert [r.status for r in notifier.results] == ["WARN"]          # WARN notifica


def test_fail_blocks_publish(broken_run):
    notifier = CaptureNotifier()
    gate = run_quality_gate("bronze", broken_run.run_id, provider="trafficjunky", checks=one_spec("trafficjunky_duplicates"),
                            persist=False, notifier=notifier)
    assert gate.status == "FAIL" and gate.publish_allowed is False
    assert [r.status for r in notifier.results] == ["FAIL"]           # FAIL notifica


def test_pass_does_not_notify(healthy_run):
    notifier = CaptureNotifier()
    gate = run_quality_gate("bronze", healthy_run.run_id, provider="voluum", checks=one_spec("voluum_pagination"),
                            persist=False, notifier=notifier)
    assert gate.status == "PASS" and gate.publish_allowed and notifier.results == []


def test_gate_with_unknown_provider_is_rejected(healthy_run):
    with pytest.raises(ValueError):
        run_quality_gate("bronze", healthy_run.run_id, provider="nope")


# ----------------------------------------------------------------------------- persistencia
def test_results_are_persisted(broken_run, conn):
    rows = conn.execute("SELECT * FROM data_quality.check_results WHERE run_id = %s", (broken_run.run_id,)).fetchall()
    assert len(rows) > 100
    assert {"run_id", "checked_at", "provider", "dataset", "layer", "check_name", "dimension", "status",
            "observed_value", "expected_value", "threshold", "details"} <= set(rows[0])
    assert {r["status"] for r in rows} == {"PASS", "WARN", "FAIL"}
    assert all(isinstance(r["details"], dict) and "message" in r["details"] for r in rows)


def test_pipeline_run_is_recorded(broken_run, healthy_run, conn):
    row = conn.execute("SELECT * FROM data_quality.pipeline_runs WHERE run_id = %s", (broken_run.run_id,)).fetchone()
    assert (row["scenario"], row["status"], row["publish_allowed"]) == ("broken", "BLOCKED", False)
    assert row["gates"] == {"bronze": "FAIL", "silver": "FAIL", "semantic": "FAIL"}
    good = conn.execute("SELECT * FROM data_quality.pipeline_runs WHERE run_id = %s", (healthy_run.run_id,)).fetchone()
    assert (good["status"], good["publish_allowed"]) == ("PUBLISHED", True)


def test_current_issues_view_is_ready_for_the_chatbot(broken_run, conn):
    rows = conn.execute("SELECT * FROM data_quality.current_issues").fetchall()
    assert rows and {r["status"] for r in rows} <= {"WARN", "FAIL"}
    assert all(r["message"] for r in rows)


# ----------------------------------------------------------------------------- healthy vs broken
def test_healthy_has_no_critical_failure_and_publishes(healthy_run, get_results):
    assert healthy_run.publish_allowed and healthy_run.published
    assert healthy_run.gates == {"bronze": "PASS", "silver": "PASS", "semantic": "PASS"}
    assert {r["status"] for r in get_results(healthy_run.run_id).values()} == {"PASS"}


def test_broken_blocks_publish_and_keeps_the_last_good_data(healthy_run, broken_run, conn):
    assert not broken_run.published and not broken_run.publish_allowed
    assert broken_run.states["publish"] == "failed" and "PublishBlocked" in broken_run.errors["publish"]
    published_runs = {r["run_id"] for r in conn.execute("SELECT DISTINCT run_id FROM analytics.published_campaign_performance_daily")}
    assert broken_run.run_id not in published_runs                     # nada do run partido chegou aos consumidores
    assert healthy_run.run_id in published_runs or published_runs     # os consumidores continuam com dados antigos e bons


def test_fail_never_deletes_bronze_or_silver(broken_run, conn):
    assert conn.execute("SELECT count(*) AS n FROM raw.voluum_report WHERE run_id = %s", (broken_run.run_id,)).fetchone()["n"] == 50
    assert conn.execute("SELECT count(*) AS n FROM analytics.campaign_performance_daily WHERE run_id = %s",
                        (broken_run.run_id,)).fetchone()["n"] > 0


def test_notifications_match_warn_and_fail_results(broken_run, conn):
    non_pass = conn.execute("SELECT count(*) AS n FROM data_quality.check_results WHERE run_id = %s AND status <> 'PASS'",
                            (broken_run.run_id,)).fetchone()["n"]
    assert len(broken_run.notifier.results) == non_pass > 0
    assert all(r.status in ("WARN", "FAIL") for r in broken_run.notifier.results)


def test_console_notifier_persists_alerts(conn, capsys):
    conn.execute("DELETE FROM data_quality.alerts WHERE run_id = 'alert-test'")
    result = CheckResult("alert-test", __import__("datetime").datetime.now(), "voluum", "voluum_report", "bronze",
                         "pagination_complete", "completeness", "FAIL", 2000, 4321, 4321, {"message": "pagination incomplete"})
    ConsoleNotifier(conn).notify(result)
    out = capsys.readouterr().out
    assert "[DQ ALERT]" in out and "provider=voluum" in out and "check=pagination_complete" in out
    assert "status=FAIL" in out and "observed=2000" in out and "expected=4321" in out
    row = conn.execute("SELECT * FROM data_quality.alerts WHERE run_id = 'alert-test'").fetchone()
    assert (row["check_name"], row["provider"], row["status"], row["destination"]) == ("pagination_complete", "voluum", "FAIL", "console")
    assert row["sent_at"] is not None


# ----------------------------------------------------------------------------- notifier
def test_webhook_is_optional_and_never_called_without_url(monkeypatch):
    class S:
        webhook_url = ""

    notifier = get_notifier(settings=S())
    assert [type(n) for n in notifier.notifiers] == [ConsoleNotifier]
    S.webhook_url = "https://example.invalid/hook"
    assert [type(n) for n in get_notifier(settings=S()).notifiers] == [ConsoleNotifier, WebhookNotifier]


def test_webhook_payload_shape(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout=0):
        sent["url"], sent["body"] = request.full_url, json.loads(request.data)

        class R:
            def close(self):
                pass
        return R()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = CheckResult("run-1", __import__("datetime").datetime.now(), "trafficjunky", "campaign_stats", "silver",
                         "daily_spend_change", "volume", "WARN", -0.63, 1260, -0.40, {"message": "m"})
    WebhookNotifier("https://example.invalid/hook").notify(result)
    assert sent["url"] == "https://example.invalid/hook"
    assert {"provider", "dataset", "layer", "check", "status", "observed", "threshold", "run_id"} <= set(sent["body"])
    assert sent["body"]["check"] == "daily_spend_change" and sent["body"]["observed"] == -0.63 and sent["body"]["threshold"] == -0.40
    assert build_payload(result)["run_id"] == "run-1"


def test_webhook_failure_does_not_break_the_run(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    result = CheckResult("r", __import__("datetime").datetime.now(), "p", "d", "bronze", "c", "x", "FAIL")
    WebhookNotifier("https://example.invalid/hook").notify(result)      # nao levanta
    assert "webhook delivery failed" in capsys.readouterr().err


# ----------------------------------------------------------------------------- modo strict (como no Airflow)
def test_strict_mode_stops_the_pipeline_at_the_first_failed_gate(db):
    result = run_pipeline("broken", gate_mode="strict", notifier=CaptureNotifier(), log=lambda *_: None)
    assert result.states["bronze_quality"] == "failed" and "GateFailed" in result.errors["bronze_quality"]
    assert [result.states[t] for t in ("normalize", "silver_quality", "semantic_quality", "publish")] == ["upstream_failed"] * 4
    assert result.states["notify"] == "success"                    # trigger_rule all_done: corre sempre
    assert not result.published and set(result.gates) == {"bronze"}


def test_provider_filter_runs_only_that_provider(db, get_results):
    result = run_pipeline("broken", providers=("voluum",), gate_mode="observe", notifier=CaptureNotifier(), log=lambda *_: None)
    providers = {p for p, _ in get_results(result.run_id)}
    assert providers == {"voluum", "platform"}
