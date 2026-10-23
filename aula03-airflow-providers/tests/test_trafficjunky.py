"""TrafficJunky: do raw ao canonico, e a reconciliacao."""

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from contracts.trafficjunky import TJStatsPage
from pipeline import load, reconcile
from pipeline.config import get_settings
from pipeline.validate import ContractViolation, read_json, validate_canonical
from providers import trafficjunky as tj

DAY = date(2026, 10, 20)
A, B = UUID("0b6116c0-9ed5-5398-8df0-72911f86933f"), UUID("b460c5a8-bdb2-5de4-bf36-2434c148a088")
MAPPING = {"Campaign A": A, "Campaign B": B}


def stat(name, cost, impressions=1000, clicks=10, kind="standard"):
    return {"campaign_name": name, "campaign_type": kind, "impressions": impressions,
            "clicks": clicks, "cost": Decimal(cost)}


# --- transform: funcao pura ----------------------------------------------------

def test_deals_are_skipped():
    rows, counts = tj.build_canonical([stat("Campaign A", "5"), stat("Campaign A", "99", kind="deal")], MAPPING, DAY, "EUR")
    assert len(rows) == 1 and counts["deals_skipped"] == 1 and rows[0]["cost"] == Decimal("5.0000")


def test_campaigns_are_matched_to_ours_by_name():
    rows, _ = tj.build_canonical([stat("Campaign B", "1")], MAPPING, DAY, "EUR")
    assert rows[0]["campaign_id"] == str(B) and rows[0]["provider"] == "trafficjunky"
    assert rows[0]["source_specific_id"] is None  # o TrafficJunky nao tem este nivel


def test_unmapped_campaigns_are_dropped_and_logged_not_fatal(caplog):
    rows, counts = tj.build_canonical([stat("Campaign A", "5"), stat("Ghost", "40")], MAPPING, DAY, "EUR")
    assert [r["campaign_id"] for r in rows] == [str(A)]
    assert counts["unmapped_dropped"] == 1 and counts["unmapped_names"] == ["Ghost"]
    assert "Ghost" in caplog.text and any(r.levelname == "CRITICAL" for r in caplog.records)


def test_duplicate_names_are_merged_summing_the_base_metrics():
    rows, counts = tj.build_canonical(
        [stat("Campaign A", "5.10", 1000, 10), stat("Campaign A", "2.25", 500, 4)], MAPPING, DAY, "EUR")
    assert counts["merged"] == 1 and len(rows) == 1
    assert (rows[0]["impressions"], rows[0]["clicks"], rows[0]["cost"]) == (1500, 14, Decimal("7.3500"))


def test_money_stays_decimal_without_float_artifacts():
    rows, _ = tj.build_canonical([stat("Campaign A", "0.10"), stat("Campaign A", "0.20")], MAPPING, DAY, "EUR")
    assert rows[0]["cost"] == Decimal("0.3000")  # com float seria 0.30000000000000004


def test_provider_ratios_are_not_carried_over():
    rows, _ = tj.build_canonical([{**stat("Campaign A", "5"), "ecpc": Decimal("0.5")}], MAPPING, DAY, "EUR")
    assert set(rows[0]) == {"date", "provider", "campaign_id", "source_specific_id", "currency",
                            "impressions", "clicks", "cost"}


def test_nothing_to_transform():
    assert tj.build_canonical([], MAPPING, DAY, "EUR")[0] == []
    rows, counts = tj.build_canonical([stat("Ghost", "1")], MAPPING, DAY, "EUR")
    assert rows == [] and counts["unmapped_dropped"] == 1


# --- extract / validate_source (mock em memoria) ---------------------------------

def test_extract_paginates_and_stores_the_raw_response(env):
    meta = tj.extract(DAY)
    assert meta["pages"] == 2 and meta["rows_fetched"] == 7  # PAGE_SIZE=5
    raw = json.loads(open(meta["raw_path"]).read())
    assert len(raw["pages"]) == 2 and raw["pages"][0]["total"] == 7
    assert meta["raw_path"].endswith("trafficjunky/date=2026-10-20/response.json")
    assert set(meta) >= {"provider", "date", "raw_path", "currency"}  # so metadados, nunca dados


def test_extract_is_overwritten_not_accumulated(env):
    first = tj.extract(DAY)["raw_path"]
    assert tj.extract(DAY)["raw_path"] == first


def test_check_api_fails_when_the_provider_is_down(env):
    import httpx
    assert tj.check_api()["status"] == "ok"
    env.post("/admin/trafficjunky/mode/http_500")
    with pytest.raises(httpx.HTTPStatusError):
        tj.check_api()


def test_validate_source_passes_on_healthy_data(env):
    assert tj.validate_source(tj.extract(DAY))["source_valid"] is True


def test_validate_source_fails_on_schema_drift(env):
    env.post("/admin/trafficjunky/mode/schema_drift")
    with pytest.raises(ContractViolation, match="data.\\*.cost -> missing"):
        tj.validate_source(tj.extract(DAY))


def test_validate_source_fails_on_wrong_types(env, tmp_path):
    meta = tj.extract(DAY)
    raw = json.loads(open(meta["raw_path"]).read())
    raw["pages"][0]["data"][0]["clicks"] = "dez"
    open(meta["raw_path"], "w").write(json.dumps(raw))
    with pytest.raises(ContractViolation, match="clicks"):
        tj.validate_source(meta)


def test_source_contract_ignores_unknown_extra_fields():
    TJStatsPage.model_validate({"data": [{**{"campaign_name": "x", "campaign_type": "s", "impressions": 1,
                                             "clicks": 1, "cost": 1}, "brand_new_field": 1}],
                                "total": 1, "limit": 5, "offset": 0, "extra": True})


# --- pipeline completa + reconciliacao (BD real) -----------------------------------

def run(day=DAY):
    meta = tj.extract(day)
    meta = tj.validate_source(meta)
    meta = tj.transform(meta)
    meta = validate_canonical(meta)
    meta = load.run_load(meta)
    total, currency = tj.fetch_api_total(meta)
    return reconcile.run_reconcile(meta, total, currency), meta


def test_full_pipeline_healthy_reconciles(env, conn):
    out, _ = run()
    assert out["reconciliation"]["status"] == "PASS" and out["reconciliation"]["difference"] == "0.0000"
    assert out["counts"] == {"fetched": 7, "deals_skipped": 1, "unmapped_dropped": 0,
                             "unmapped_names": [], "merged": 1, "saved": 5}
    assert conn.execute("SELECT count(*) FROM fact_campaign_daily WHERE source_specific_id IS NULL").fetchone()[0] == 5


def test_running_the_same_day_twice_does_not_duplicate(env, conn):
    first, _ = run()
    second, _ = run()
    third, _ = run()
    assert conn.execute("SELECT count(*) FROM fact_campaign_daily").fetchone()[0] == 5
    assert first["loaded"] == {"inserted": 5, "updated": 0}
    assert third["loaded"] == {"inserted": 0, "updated": 5}


def test_partial_data_load_succeeds_but_reconcile_fails(env, conn):
    """O momento da aula: HTTP 200, source PASS, transform PASS, canonical PASS, load PASS, reconcile FAIL."""
    env.post("/admin/trafficjunky/mode/partial_data")
    meta = tj.validate_source(tj.extract(DAY))              # PASS
    meta = tj.transform(meta)                                # PASS
    meta = validate_canonical(meta)                          # PASS
    meta = load.run_load(meta)                               # PASS (carregou o que recebeu)
    total, currency = tj.fetch_api_total(meta)               # o total de controlo e o REAL
    with pytest.raises(reconcile.ReconciliationFailed, match="diferenca"):
        reconcile.run_reconcile(meta, total, currency)


def test_dirty_data_drops_the_unmapped_campaign_and_reconcile_reveals_the_loss(env, conn):
    env.post("/admin/trafficjunky/mode/dirty_data")
    meta = tj.transform(tj.validate_source(tj.extract(DAY)))
    assert meta["counts"]["unmapped_names"] == ["TJ Unmapped Campaign Test"]
    meta = load.run_load(validate_canonical(meta))
    total, currency = tj.fetch_api_total(meta)
    with pytest.raises(reconcile.ReconciliationFailed):
        reconcile.run_reconcile(meta, total, currency)


def test_refetch_strategy_is_NOT_independent_of_the_detail(env, conn, monkeypatch):
    """Com 'refetch_stats' o total e calculado sobre o mesmo detalhe truncado: a falha passa despercebida."""
    monkeypatch.setenv("TRAFFICJUNKY_TOTAL_STRATEGY", "refetch_stats")
    env.post("/admin/trafficjunky/mode/partial_data")
    out, _ = run()
    assert out["reconciliation"]["status"] == "PASS"  # enganou-se: os dois estao truncados


def test_refetch_strategy_matches_the_summary_when_healthy(env, monkeypatch):
    meta = tj.extract(DAY)
    summary, _ = tj.fetch_api_total(meta)
    monkeypatch.setenv("TRAFFICJUNKY_TOTAL_STRATEGY", "refetch_stats")
    assert tj.fetch_api_total(meta)[0] == summary


def test_unknown_total_strategy_is_rejected(env, monkeypatch):
    monkeypatch.setenv("TRAFFICJUNKY_TOTAL_STRATEGY", "magic")
    with pytest.raises(ValueError, match="magic"):
        tj.fetch_api_total(tj.extract(DAY))


def test_reconcile_compares_per_currency(env, conn):
    _, meta = run()
    with pytest.raises(reconcile.ReconciliationFailed, match="moedas diferentes"):
        reconcile.run_reconcile(meta, Decimal("1"), api_currency="USD")


def test_transform_works_on_a_brand_new_database(env, db_url):
    """1.a run numa BD vazia: o transform corre ANTES do load, por isso cria o schema (bug apanhado no Docker)."""
    meta = tj.validate_source(tj.extract(DAY))
    out = tj.transform(meta)  # sem a fixture `conn`: nao ha tabelas
    assert out["counts"]["saved"] == 5
