"""Erobella: o link, o transform e a reconciliacao."""

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from pipeline import load, reconcile
from pipeline.validate import ContractViolation, validate_canonical
from providers import erobella as eb
from providers.erobella import extract_campaign_id

DAY = date(2026, 10, 20)
U1 = UUID("0b6116c0-9ed5-5398-8df0-72911f86933f")
U2 = UUID("85e7e1f3-64a2-50c6-a56a-5f6fa9915c19")
KNOWN = {U1, U2}


# --- extract_campaign_id: a funcao pequena e testada ---------------------------

@pytest.mark.parametrize("link", [
    f"https://trk.example/{U1}?creative=a",                 # UUID no caminho
    f"https://trk.example/{U1}",                            # ... no fim
    f"https://trk.example/{U1}/",                           # ... com barra
    f"https://trk.example/{U1}#frag",
    f"https://trk.example/click?vcid={U1}&creative=a",      # parametro vcid
    f"https://trk.example/click?x=1&vcid={U1}",
    f"https://trk.example/{str(U1).upper()}?creative=a",    # maiusculas
])
def test_extracts_the_uuid(link):
    assert extract_campaign_id(link) == U1


@pytest.mark.parametrize("link", [
    None, "", "https://trk.example/landing?creative=a",
    "https://trk.example/not-a-uuid?x=1",
    f"https://trk.example/{str(U1)[:-1]}?x=1",              # UUID truncado
    f"https://trk.example/{U1}extra?x=1",                   # colado a mais texto
    "vcid=" + str(U1)[:20],
])
def test_returns_none_when_there_is_no_uuid(link):
    assert extract_campaign_id(link) is None


def test_vcid_wins_when_both_formats_are_present():
    assert extract_campaign_id(f"https://t.example/{U1}?vcid={U2}") == U2


# --- transform: funcao pura -------------------------------------------------------

def perf(label, cost="10.00", impressions=1000, clicks=10, day="2026-10-20"):
    return {"date": day, "label": label, "impressions": impressions, "clicks": clicks, "cost_eur": Decimal(cost)}


def creative(label, link):
    return {"label": label, "link": link}


def test_each_creative_becomes_one_row_with_the_label_as_source_specific_id():
    rows, counts = eb.build_canonical(
        [perf("a"), perf("b")], [creative("a", f"https://t/{U1}?x"), creative("b", f"https://t/c?vcid={U1}")],
        KNOWN, DAY, "EUR")
    assert [(r["source_specific_id"], r["campaign_id"]) for r in rows] == [("a", str(U1)), ("b", str(U1))]
    assert counts["saved"] == 2 and rows[0]["provider"] == "erobella" and rows[0]["currency"] == "EUR"


def test_creatives_of_different_campaigns_keep_their_own_campaign():
    rows, _ = eb.build_canonical([perf("a"), perf("b")],
                                 [creative("a", f"https://t/{U1}"), creative("b", f"https://t/{U2}")], KNOWN, DAY, "EUR")
    assert {r["source_specific_id"]: r["campaign_id"] for r in rows} == {"a": str(U1), "b": str(U2)}


def test_creative_without_link_or_uuid_is_dropped_and_logged_not_fatal(caplog):
    rows, counts = eb.build_canonical(
        [perf("ok", "5"), perf("nolink", "7"), perf("nouuid", "9"), perf("orphan", "1")],
        [creative("ok", f"https://t/{U1}"), creative("nolink", None), creative("nouuid", "https://t/landing")],
        KNOWN, DAY, "EUR")  # "orphan" nem sequer existe em by_creative
    assert [r["source_specific_id"] for r in rows] == ["ok"]
    assert (counts["no_link_dropped"], counts["no_campaign_id_dropped"]) == (2, 1)
    assert counts["dropped_labels"] == ["nolink", "nouuid", "orphan"]
    assert any(r.levelname == "CRITICAL" for r in caplog.records)


def test_a_uuid_that_is_not_one_of_our_campaigns_is_dropped():
    rows, counts = eb.build_canonical([perf("a")], [creative("a", "https://t/00000000-0000-0000-0000-000000000000")],
                                      KNOWN, DAY, "EUR")
    assert rows == [] and counts["unknown_campaign_dropped"] == 1


def test_other_days_in_the_response_are_ignored():
    rows, counts = eb.build_canonical([perf("a"), perf("a", day="2026-10-21")], [creative("a", f"https://t/{U1}")],
                                      KNOWN, DAY, "EUR")
    assert len(rows) == 1 and counts["other_days_skipped"] == 1


def test_money_is_exact_and_ratios_are_not_carried_over():
    rows, _ = eb.build_canonical([{**perf("a", "0.10"), "ctr_pct": Decimal("1.5")}], [creative("a", f"https://t/{U1}")],
                                 KNOWN, DAY, "EUR")
    assert rows[0]["cost"] == Decimal("0.1000") and "ctr_pct" not in rows[0] and "cpc" not in rows[0]


def test_nothing_to_transform():
    assert eb.build_canonical([], [], KNOWN, DAY, "EUR")[0] == []
    assert eb.build_canonical([perf("a")], [], KNOWN, DAY, "EUR")[0] == []


# --- extract / validate_source (mock em memoria) ---------------------------------------

def test_extract_stores_the_three_part_response_as_it_came(env):
    meta = eb.extract(DAY)
    assert meta["pages"] == 1 and meta["rows_fetched"] == 7
    (page,) = json.loads(open(meta["raw_path"]).read())["pages"]
    assert set(page) == {"by_day_creative", "by_creative", "by_day"}
    assert meta["raw_path"].endswith("erobella/date=2026-10-20/response.json")


def test_validate_source_passes_on_healthy_data(env):
    assert eb.validate_source(eb.extract(DAY))["source_valid"] is True


def test_validate_source_fails_on_schema_drift(env):
    env.post("/admin/erobella/mode/schema_drift")
    with pytest.raises(ContractViolation, match="by_day_creative.\\*.cost_eur -> missing"):
        eb.validate_source(eb.extract(DAY))


def test_check_api_fails_when_the_provider_is_down(env):
    import httpx
    env.post("/admin/erobella/mode/http_500")
    with pytest.raises(httpx.HTTPStatusError):
        eb.check_api()


# --- pipeline completa + reconciliacao (BD real) -------------------------------------------

def run(day=DAY):
    meta = eb.validate_source(eb.extract(day))
    meta = eb.transform(meta)
    meta = validate_canonical(meta)
    meta = load.run_load(meta)
    total, currency = eb.fetch_api_total(meta)
    return reconcile.run_reconcile(meta, total, currency), meta


def test_full_pipeline_healthy_reconciles(env, conn):
    out, _ = run()
    assert out["reconciliation"]["status"] == "PASS"
    assert out["counts"]["saved"] == 7
    labels = [r[0] for r in conn.execute("SELECT source_specific_id FROM fact_campaign_daily ORDER BY 1")]
    assert labels[0] == "br-keto-a" and len(labels) == 7


def test_running_the_same_day_twice_does_not_duplicate(env, conn):
    run(); run()
    assert conn.execute("SELECT count(*) FROM fact_campaign_daily").fetchone()[0] == 7


def test_partial_data_load_succeeds_but_reconcile_fails(env, conn):
    env.post("/admin/erobella/mode/partial_data")
    meta = eb.transform(eb.validate_source(eb.extract(DAY)))
    meta = load.run_load(validate_canonical(meta))
    total, currency = eb.fetch_api_total(meta)  # by_day: o total REAL
    with pytest.raises(reconcile.ReconciliationFailed, match="diferenca"):
        reconcile.run_reconcile(meta, total, currency)


def test_dirty_data_drops_creatives_and_reconcile_reveals_the_loss(env, conn):
    env.post("/admin/erobella/mode/dirty_data")
    meta = eb.transform(eb.validate_source(eb.extract(DAY)))
    assert meta["counts"]["no_link_dropped"] == 1 and meta["counts"]["no_campaign_id_dropped"] == 1
    assert meta["counts"]["dropped_labels"] == ["bad-link", "orphan-no-link"]
    meta = load.run_load(validate_canonical(meta))
    total, currency = eb.fetch_api_total(meta)
    with pytest.raises(reconcile.ReconciliationFailed):
        reconcile.run_reconcile(meta, total, currency)


def test_the_two_providers_are_independent(env, conn):
    """TrafficJunky partido, Erobella saudavel: cada um tem o seu estado e a sua reconciliacao."""
    from providers import trafficjunky as tj
    env.post("/admin/trafficjunky/mode/http_500")
    with pytest.raises(Exception):
        tj.check_api()
    out, _ = run()
    assert out["reconciliation"]["status"] == "PASS"
