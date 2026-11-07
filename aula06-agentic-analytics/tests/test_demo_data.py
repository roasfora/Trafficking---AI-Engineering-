"""Integracao: os numeros das demos da aula estao mesmo na base de dados."""

import pytest

from tools.postgres import run_postgres_query

pytestmark = pytest.mark.usefixtures("pg")
T = "marketing.campaign_performance_daily"


def rows(sql):
    result = run_postgres_query(sql)
    assert "error" not in result, result
    return result["rows"]


def test_80_rows_grain_unique():
    assert rows(f"SELECT COUNT(*), COUNT(DISTINCT (date, provider, campaign_id)) FROM {T}") == [[80, 80]]


def test_demo1_erobella_spend():
    assert rows(f"SELECT SUM(cost) FROM {T} WHERE provider='erobella' AND date='2026-11-05'") == [[426.28]]


def test_demo_cpc_correct_vs_average_of_ratios():
    window = "date BETWEEN '2026-10-30' AND '2026-11-05'"
    correct = dict(rows(f"SELECT provider, ROUND(SUM(cost)/SUM(clicks), 4) FROM {T} WHERE {window} GROUP BY 1"))
    wrong = dict(rows(f"SELECT provider, ROUND(CAST(AVG(cost/clicks) AS numeric), 4) FROM {T} WHERE {window} GROUP BY 1"))
    assert correct == {"trafficjunky": 0.2699, "erobella": 0.2367}
    assert wrong["erobella"] == 0.3374


def test_anomaly_row():
    assert rows(f"SELECT clicks, cost FROM {T} WHERE date='2026-11-02' AND campaign_name='EB ES Sports Native'") == [[12, 30.0]]


def test_cr_numbers():
    sql = f"SELECT date, {{dim}}, ROUND(100.0*SUM(conversions)/SUM(clicks), 2) FROM {T} WHERE date IN ('2026-11-04','2026-11-05') GROUP BY 1, 2"
    total = {(d, k): v for d, k, v in rows(sql.format(dim="'total'"))}
    assert (total["2026-11-04", "total"], total["2026-11-05", "total"]) == (8.15, 7.28)
    prov = {(d, k): v for d, k, v in rows(sql.format(dim="provider"))}
    assert prov["2026-11-04", "trafficjunky"] == 8.32 and prov["2026-11-05", "trafficjunky"] == 8.33
    assert prov["2026-11-04", "erobella"] == 7.90 and prov["2026-11-05", "erobella"] == 6.03
    camp = {(d, k): v for d, k, v in rows(sql.format(dim="campaign_name"))}
    assert camp["2026-11-04", "EB ES Sports Native"] == 8.57 and camp["2026-11-05", "EB ES Sports Native"] == 2.09


def test_agent_role_is_read_only():
    result = run_postgres_query(f"UPDATE {T} SET cost = 0")
    assert "rejected" in result["error"]  # o guard barra primeiro...
    import psycopg
    from tools.postgres import connect
    with pytest.raises(psycopg.Error):  # ...e a base de dados barraria na mesma
        with connect() as conn:
            conn.read_only = False
            conn.execute(f"UPDATE {T} SET cost = 0")


def test_agent_role_sees_only_one_table():
    import psycopg
    from tools.postgres import connect
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connect() as conn:
            conn.execute("SELECT * FROM pg_catalog.pg_authid")
