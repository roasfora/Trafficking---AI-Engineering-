"""Idempotencia, e a armadilha do NULL na chave. Precisa de `docker compose up -d postgres`."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from contracts.canonical import CampaignDailyStat
from pipeline import load

C1 = UUID("0b6116c0-9ed5-5398-8df0-72911f86933f")  # TJ PT Casino Desktop (dim_campaign)
C2 = UUID("85e7e1f3-64a2-50c6-a56a-5f6fa9915c19")  # EB PT Casino Native
DAY = date(2026, 10, 20)


def stat(**kw):
    base = dict(date=DAY, provider="trafficjunky", campaign_id=C1, source_specific_id=None,
                currency="EUR", impressions=1000, clicks=25, cost=Decimal("12.34"))
    return CampaignDailyStat(**{**base, **kw})


def count(conn, table="fact_campaign_daily"):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_dimension_is_seeded_and_mappable_by_name(conn):
    mapping = load.campaign_mapping(conn)
    assert len(mapping) == 8 and mapping["TJ PT Casino Desktop"] == C1


def test_trafficjunky_row_with_null_key_is_not_duplicated(conn):
    """O teste da aula: duas cargas da MESMA linha TrafficJunky (source_specific_id NULL)."""
    rows = [stat()]
    first = load.upsert_stats(conn, rows)
    second = load.upsert_stats(conn, rows)
    assert count(conn) == 1
    assert first == {"inserted": 1, "updated": 0}
    assert second == {"inserted": 0, "updated": 1}


def test_updated_values_replace_the_old_ones(conn):
    load.upsert_stats(conn, [stat(cost=Decimal("10"))])
    load.upsert_stats(conn, [stat(cost=Decimal("11.5"))])
    assert conn.execute("SELECT cost FROM fact_campaign_daily").fetchone()[0] == Decimal("11.5000")


def test_loaded_at_is_kept_and_updated_at_moves(conn):
    load.upsert_stats(conn, [stat()])
    loaded1, updated1 = conn.execute("SELECT loaded_at, updated_at FROM fact_campaign_daily").fetchone()
    load.upsert_stats(conn, [stat()])
    loaded2, updated2 = conn.execute("SELECT loaded_at, updated_at FROM fact_campaign_daily").fetchone()
    assert loaded1 == loaded2 and updated2 > updated1


def test_erobella_creatives_are_distinct_rows_by_source_specific_id(conn):
    rows = [stat(provider="erobella", campaign_id=C2, source_specific_id="creative-a"),
            stat(provider="erobella", campaign_id=C2, source_specific_id="creative-b")]
    load.upsert_stats(conn, rows)
    load.upsert_stats(conn, rows)
    assert count(conn) == 2


def test_same_campaign_two_providers_are_different_rows(conn):
    load.upsert_stats(conn, [stat(), stat(provider="erobella")])
    assert count(conn) == 2


def test_a_plain_unique_constraint_would_duplicate_null_rows(conn):
    """Porque e que a constraint tem NULLS NOT DISTINCT: sem ela, NULL != NULL."""
    conn.execute("CREATE TABLE naive_unique (LIKE fact_campaign_daily INCLUDING DEFAULTS)")
    conn.execute("ALTER TABLE naive_unique ADD CONSTRAINT uq_plain UNIQUE (date, provider, campaign_id, source_specific_id)")
    for _ in range(3):
        load.upsert_stats(conn, [stat()], table="naive_unique")
    assert count(conn, "naive_unique") == 3  # triplicou, sem nenhum erro


def test_naive_insert_duplicates(conn):
    conn.execute("CREATE TABLE naive (LIKE fact_campaign_daily INCLUDING DEFAULTS)")
    for _ in range(3):
        load.naive_insert(conn, "naive", [stat()])
    assert count(conn, "naive") == 3


def test_empty_string_is_not_a_valid_source_specific_id(conn):
    with pytest.raises(Exception):
        stat(source_specific_id="")  # contrato canonico
    with pytest.raises(psycopg.errors.CheckViolation):  # e a base de dados tambem recusa
        conn.execute(
            "INSERT INTO fact_campaign_daily (date, provider, campaign_id, source_specific_id, currency, impressions, clicks, cost) "
            "VALUES ('2026-10-20', 'erobella', %s, '', 'EUR', 1, 1, 1)", (C2,))


def test_unknown_campaign_violates_the_foreign_key(conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        load.upsert_stats(conn, [stat(campaign_id=UUID("00000000-0000-0000-0000-000000000000"))])


def test_load_is_one_transaction(conn):
    good, bad = stat(), stat(campaign_id=UUID("00000000-0000-0000-0000-000000000000"))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with conn.transaction():
            load.upsert_stats(conn, [good, bad])
    assert count(conn) == 0  # nem a linha boa ficou
