import pytest

from tools.sql_guard import SqlRejected, check_sql

T = "analytics.campaign_performance_daily"


def test_accepts_simple_select():
    assert check_sql(f"SELECT * FROM {T} LIMIT 10;") == f"SELECT * FROM {T} LIMIT 10"


def test_accepts_cte_select():
    sql = f"WITH x AS (SELECT * FROM {T}) SELECT * FROM x"
    assert "WITH x AS" in check_sql(sql)


def test_accepts_aggregate_with_date_filter():
    check_sql(
        f"SELECT provider, SUM(cost) / NULLIF(SUM(clicks), 0) FROM {T} "
        "WHERE date BETWEEN '2026-10-30' AND '2026-11-05' GROUP BY 1"
    )


@pytest.mark.parametrize("sql", [
    f"DROP TABLE {T}",
    f"DELETE FROM {T}",
    f"UPDATE {T} SET cost = 0",
    f"INSERT INTO {T} SELECT * FROM {T}",
    f"TRUNCATE {T}",
    f"ALTER TABLE {T} ADD COLUMN x int",
    "CREATE TABLE t AS SELECT 1",
    f"COPY {T} TO '/tmp/x'",
    "GRANT ALL ON analytics.campaign_performance_daily TO public",
    "REVOKE ALL ON analytics.campaign_performance_daily FROM public",
    f"MERGE INTO {T} t USING {T} s ON t.date = s.date WHEN MATCHED THEN DELETE",
    f"SELECT * INTO copia FROM {T}",
    f"WITH x AS (DELETE FROM {T} RETURNING *) SELECT * FROM x",
])
def test_rejects_non_select(sql):
    with pytest.raises(SqlRejected):
        check_sql(sql)


def test_rejects_multiple_statements():
    with pytest.raises(SqlRejected, match="one statement"):
        check_sql("SELECT 1; DROP TABLE users")


def test_rejects_other_schema():
    with pytest.raises(SqlRejected):
        check_sql("SELECT * FROM secret.users")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM users",                                   # sem schema
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT * FROM information_schema.tables",
    f"SELECT * FROM other_db.{T}",                            # catalogo desconhecido
    f"SELECT * FROM {T} WHERE cost > (SELECT 1 FROM secret.t)",   # subquery
    f"SELECT * FROM {T} a JOIN secret.users b ON true",       # join
    f"SELECT * FROM (SELECT * FROM {T}) q, secret.users",
    f"WITH x AS (SELECT * FROM {T}) SELECT * FROM x, secret.users",  # CTE
])
def test_rejects_tables_outside_allowlist(sql):
    with pytest.raises(SqlRejected):
        check_sql(sql)


def test_rejects_cte_shadowing_in_sibling_scope():
    # `pg_shadow` so existe como CTE dentro da subquery; fora dela e a tabela real.
    sql = "SELECT * FROM (WITH pg_shadow AS (SELECT 1 AS a) SELECT a FROM pg_shadow) q, pg_shadow"
    with pytest.raises(SqlRejected):
        check_sql(sql)


def test_rejects_forward_cte_reference():
    with pytest.raises(SqlRejected):
        check_sql("WITH a AS (SELECT * FROM b), b AS (SELECT 1) SELECT * FROM a")


def test_cte_named_like_secret_table_does_not_open_qualified_access():
    with pytest.raises(SqlRejected):
        check_sql("WITH users AS (SELECT 1) SELECT * FROM secret.users")


@pytest.mark.parametrize("sql", [
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT set_config('role', 'postgres', false)",
    f"SELECT * FROM {T}, LATERAL pg_sleep(1)",
    "SELECT * FROM pg_read_file('/etc/passwd')",
])
def test_rejects_dangerous_functions(sql):
    with pytest.raises(SqlRejected):
        check_sql(sql)


def test_rejects_too_long():
    with pytest.raises(SqlRejected, match="longer"):
        check_sql(f"SELECT * FROM {T} WHERE provider = '{'x' * 3000}'")


def test_rejects_unparseable():
    with pytest.raises(SqlRejected):
        check_sql("SELEC FROM WHERE ((")


@pytest.mark.parametrize("sql,expected", [
    (f"SELECT * FROM {T}", "LIMIT 50"),
    (f"SELECT * FROM {T} LIMIT 10", "LIMIT 10"),
    (f"SELECT * FROM {T} LIMIT 100000", "LIMIT 50"),
])
def test_max_rows_enforced(sql, expected):
    assert check_sql(sql, max_rows=50).endswith(expected)
