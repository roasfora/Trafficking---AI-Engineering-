"""Contexto de um check: os dados que ele pode ler (Bronze, Silver, referencia), carregados sob pedido.

Os checks sao funcoes `check(spec, ctx) -> list[CheckResult]`. Em producao o contexto le do PostgreSQL;
nos testes pode receber os dados ja prontos (sem base de dados).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from config import get_settings
from ingestion.bronze_loader import TABLES
from quality.models import CheckResult
from semantic import load_semantic, metric_sql
from simulators.scenarios import window_days

BRONZE_DATASET = {"erobella": "erobella_daily_stats", "trafficjunky": "trafficjunky_campaign_stats", "voluum": "voluum_report"}
_UNSET = object()


def _clean(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def fetch_rows(conn, sql: str, params: Any = None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [{k: _clean(v) for k, v in row.items()} for row in cur.fetchall()]


class CheckContext:
    def __init__(self, run_id: str, provider: str, layer: str, conn=None, checked_at: datetime | None = None,
                 as_of: date | None = None, window: int | None = None, semantic: dict | None = None,
                 api_run: Any = _UNSET, bronze_rows: Any = _UNSET, silver_rows: Any = _UNSET,
                 fx_rates: Any = _UNSET, control_rows: Any = _UNSET, known_campaigns: Any = _UNSET):
        settings = get_settings()
        self.run_id, self.provider, self.layer, self.conn = run_id, provider, layer, conn
        self.checked_at = checked_at or datetime.now(timezone.utc)
        self.as_of = as_of or settings.as_of_date
        self.window = window or settings.window_days
        self.semantic = semantic or load_semantic()
        self._cache = {k: v for k, v in dict(bronze_rows=bronze_rows, silver_rows=silver_rows,
                                             fx_rates=fx_rates, control_rows=control_rows,
                                             known_campaigns=known_campaigns).items() if v is not _UNSET}
        if api_run is not _UNSET:  # a propriedade espera uma lista de linhas (como o resultado da query)
            self._cache["api_run"] = [] if api_run is None else [api_run]

    # -------------------------------------------------------------- dados
    @property
    def expected_days(self) -> list[date]:
        return window_days(self.as_of, self.window)

    def _load(self, key: str, sql: str, params: Any = None) -> Any:
        if key not in self._cache:
            if self.conn is None:
                raise RuntimeError(f"CheckContext without a connection cannot load '{key}'")
            self._cache[key] = fetch_rows(self.conn, sql, params)
        return self._cache[key]

    @property
    def api_run(self) -> dict | None:
        rows = self._load("api_run", "SELECT * FROM raw.api_runs WHERE run_id = %s AND provider = %s",
                          (self.run_id, self.provider))
        return rows[0] if rows else None

    @property
    def bronze_rows(self) -> list[dict]:
        table = TABLES[self.provider]
        return self._load("bronze_rows", f"SELECT * FROM {table} WHERE run_id = %s ORDER BY day", (self.run_id,))

    @property
    def silver_rows(self) -> list[dict]:
        return self._load("silver_rows", """SELECT * FROM analytics.campaign_performance_daily
                                            WHERE run_id = %s AND provider = %s ORDER BY date, campaign_id""",
                          (self.run_id, self.provider))

    @property
    def fx_rates(self) -> dict[tuple, float]:
        """(dia ISO, moeda de origem) -> taxa para EUR."""
        if "fx_rates" not in self._cache:
            rows = fetch_rows(self.conn, "SELECT date, source_currency, rate FROM analytics.exchange_rate "
                                         "WHERE target_currency = 'EUR'")
            self._cache["fx_rates"] = {(r["date"].isoformat(), r["source_currency"]): r["rate"] for r in rows}
        return self._cache["fx_rates"]

    @property
    def control_rows(self) -> list[dict]:
        return self._load("control_rows", "SELECT date, campaign_id, revenue, investment FROM analytics.daily_control")

    @property
    def known_campaigns(self) -> set[str]:
        if "known_campaigns" not in self._cache:
            self._cache["known_campaigns"] = {r["campaign_id"] for r in
                                              fetch_rows(self.conn, "SELECT campaign_id FROM analytics.campaigns")}
        return self._cache["known_campaigns"]

    # -------------------------------------------------------------- semantica (SQL gerado do semantic.yaml)
    def semantic_value(self, metric: str, group_by: str | None = None) -> Any:
        """Valor de uma metrica do semantic.yaml sobre a Silver deste run e provider."""
        sql = metric_sql(metric, where="run_id = %s AND provider = %s", group_by=group_by, semantic=self.semantic)
        rows = fetch_rows(self.conn, sql, (self.run_id, self.provider))
        return rows if group_by else (rows[0]["value"] if rows else None)

    # -------------------------------------------------------------- construcao de resultados
    def result(self, spec: dict, status: str, observed: float | None = None, expected: float | None = None,
               threshold: float | None = None, message: str = "", suffix: str = "", dimension: str | None = None,
               **details: Any) -> CheckResult:
        return CheckResult(
            run_id=self.run_id, checked_at=self.checked_at, provider=self.provider,
            dataset=spec.get("dataset", ""), layer=self.layer, check_name=spec["name"] + suffix,
            dimension=dimension or spec.get("dimension", "consistency"), status=status,
            observed_value=None if observed is None else float(observed),
            expected_value=None if expected is None else float(expected),
            threshold=None if threshold is None else float(threshold),
            details={"message": message, **details},
        )
