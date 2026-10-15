"""Pipeline completa (extract -> quality) contra a API em memoria e um
PostgreSQL real, num schema temporario. Precisa de `docker compose up -d postgres`.
"""

from datetime import datetime, timezone

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import generator
from api.main import app
from pipeline import extract, load, quality, transform, validate
from pipeline.config import get_settings

REAL_CLIENT = httpx.Client  # (monkeypatch de extract.httpx.Client e global)
START = "2026-10-01T00:00:00+00:00"
END = "2026-10-02T00:00:00+00:00"
FACTS = ("fact_conversions", "fact_campaign_costs", "fact_daily_control")


def window(start=START, end=END):
    return datetime.fromisoformat(start), datetime.fromisoformat(end)


@pytest.fixture
def env(monkeypatch, tmp_path, db_url):
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("PIPELINE_STAGING_DIR", str(tmp_path))
    monkeypatch.setenv("PIPELINE_PAGE_SIZE", "100")  # forca varias paginas

    def fake_client(*, base_url, timeout):  # a API corre em memoria
        return TestClient(app, base_url=base_url)

    monkeypatch.setattr(extract.httpx, "Client", fake_client)
    return get_settings()


def run_all(start=START, end=END):
    meta = extract.run_extract(start, end)
    meta = validate.run_validate(meta)
    meta = transform.run_transform(meta)
    meta = load.run_load_dimensions(meta)
    meta = load.run_load_facts(meta)
    return meta


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def counts(conn):
    return {t: count(conn, t) for t in FACTS}


def test_full_pipeline_happy_path(env, conn):
    meta = run_all()
    assert meta["counts"]["campaign_costs"] > 100  # mais de uma pagina
    assert count(conn, "fact_conversions") == meta["counts"]["conversions"] > 0
    assert count(conn, "fact_campaign_costs") == meta["counts"]["campaign_costs"]
    assert count(conn, "fact_daily_control") == meta["counts"]["daily_control"] > 0
    assert (count(conn, "dim_workspace"), count(conn, "dim_campaign"), count(conn, "dim_offer")) == (2, 8, 7)

    out = quality.run_quality_check(meta)
    assert all(v == "pass" for v in out["quality"].values())


def test_nulls_survive_the_whole_journey(env, conn):
    run_all()
    nulls = conn.execute(
        "SELECT count(*) FILTER (WHERE impressions IS NULL), count(*) FILTER (WHERE impressions IS NOT NULL) "
        "FROM fact_campaign_costs"
    ).fetchone()
    assert nulls[0] > 0 and nulls[1] > 0
    assert conn.execute("SELECT count(*) FROM dim_offer WHERE country_code IS NULL").fetchone()[0] == 1


def test_rerunning_the_same_window_does_not_duplicate(env, conn):
    """Scenario 7: o mesmo dia 3 vezes -> as mesmas linhas."""
    first = run_all()
    before = counts(conn)
    for _ in range(2):
        again = run_all()
        assert counts(conn) == before
    assert first["loaded"]["fact_conversions"]["inserted"] == before["fact_conversions"]
    assert again["loaded"]["fact_conversions"] == {"inserted": 0, "updated": before["fact_conversions"]}
    assert again["loaded"]["fact_daily_control"]["inserted"] == 0


def test_two_consecutive_windows_add_up(env, conn):
    run_all(START, END)
    day1 = counts(conn)
    run_all(END, "2026-10-03T00:00:00+00:00")
    assert all(counts(conn)[t] > day1[t] for t in FACTS)


def test_load_is_one_transaction(env, conn):
    """Se falhar a meio, nada fica a meio."""
    meta = transform.run_transform(validate.run_validate(extract.run_extract(START, END)))
    load.run_load_dimensions(meta)
    # estraga o daily_control (a ultima fact): campanha inexistente -> viola a FK
    path = meta["files"]["daily_control"]
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.loc[df.index[0], "campaign_id"] = "00000000-0000-0000-0000-000000000000"
    df.to_csv(path, index=False)
    with pytest.raises(Exception):
        load.run_load_facts(meta)
    assert counts(conn) == {t: 0 for t in FACTS}  # conversions e costs tambem foram revertidos


def test_quality_check_detects_a_reconciliation_break(env, conn):
    run_all()
    conn.execute(
        "UPDATE fact_daily_control SET revenue = revenue + 100 "
        "WHERE NOT is_manual AND (date, campaign_id) = (SELECT date, campaign_id FROM fact_daily_control "
        "WHERE NOT is_manual LIMIT 1)"
    )
    conn.commit()
    failed = [r.name for r in quality.run_checks(conn, *window(), 6) if not r.passed]
    assert failed == ["reconciliacao: revenue (eventos vs daily control)"]


def test_manual_rows_are_excluded_from_reconciliation(env, conn):
    run_all()
    conn.execute("UPDATE fact_daily_control SET revenue = revenue + 100, is_manual = true")
    conn.commit()
    assert all(r.passed for r in quality.run_checks(conn, *window(), 6))


def test_quality_check_detects_postback_before_visit(env, conn):
    run_all()
    conn.execute(
        "UPDATE fact_conversions SET visit_timestamp = postback_timestamp + interval '1 hour' "
        "WHERE ctid = (SELECT ctid FROM fact_conversions LIMIT 1)"
    )
    conn.commit()
    failed = [r.name for r in quality.run_checks(conn, *window(), 6) if not r.passed]
    assert "conversion.postback_timestamp >= visit_timestamp" in failed


def test_quality_check_detects_a_source_mismatch(env, conn):
    run_all()
    other = conn.execute(
        "SELECT traffic_source_id FROM dim_traffic_source WHERE traffic_source_id <> "
        "(SELECT traffic_source_id FROM fact_conversions LIMIT 1) LIMIT 1"
    ).fetchone()[0]
    conn.execute(
        "UPDATE fact_conversions SET traffic_source_id = %s "
        "WHERE ctid = (SELECT ctid FROM fact_conversions LIMIT 1)", (other,)
    )
    conn.commit()
    failed = [r.name for r in quality.run_checks(conn, *window(), 6) if not r.passed]
    assert "conversion.traffic_source == campaign.traffic_source" in failed


def test_quality_check_detects_empty_and_stale_loads(env, conn):
    failed = {r.name for r in quality.run_checks(conn, *window(), 6) if not r.passed}
    assert {"fact_conversions: row count > 0", "fact_campaign_costs: row count > 0",
            "fact_campaign_costs: freshness"} <= failed

    meta = run_all()
    # janela mais larga do que a carregada: a ultima hora de custo esta longe do fim
    wide_end = datetime(2026, 10, 3, tzinfo=timezone.utc)
    results = quality.run_checks(conn, window()[0], wide_end, 6)
    assert "fact_campaign_costs: freshness" in {r.name for r in results if not r.passed}
    with pytest.raises(quality.QualityCheckFailed):
        quality.run_quality_check({**meta, "interval_end": wide_end.isoformat()})


def test_extract_fails_loudly_on_server_error(env, monkeypatch):
    def broken(*, base_url, timeout):
        return REAL_CLIENT(transport=httpx.MockTransport(lambda r: httpx.Response(500)), base_url=base_url)

    monkeypatch.setattr(extract.httpx, "Client", broken)
    with pytest.raises(httpx.HTTPStatusError):
        extract.check_api()


def test_naive_load_duplicates_but_upsert_does_not(env, conn):
    """A demo da aula, como teste (chave composta)."""
    day = datetime(2026, 10, 1, tzinfo=timezone.utc)
    df = transform.transform("conversions", generator.list_conversions(42, day, window()[1]))
    conn.execute("CREATE TABLE naive (LIKE fact_conversions INCLUDING DEFAULTS)")
    conn.execute("CREATE TABLE idem (LIKE fact_conversions INCLUDING ALL)")
    for _ in range(3):
        load.naive_insert(conn, "naive", df)
        load.upsert(conn, "idem", df, key=transform.KEYS["conversions"])
    assert count(conn, "naive") == 3 * len(df)
    assert count(conn, "idem") == len(df)
