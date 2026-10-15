"""QUALITY CHECK: o conjunto de dados faz sentido?

Corre DEPOIS do load e olha para o que ficou na base de dados, na janela
desta run. Complementa o `validate`:

    validate       -> cada REGISTO tem a forma certa? (Pydantic, antes do load)
    quality_check  -> o CONJUNTO faz sentido?          (SQL, depois do load)

Verificacoes:
    * row count > 0             uma carga vazia e quase sempre um erro silencioso
    * freshness                 a hora de custo mais recente esta perto do fim da janela
    * chaves unicas             sem linhas repetidas pela chave (composta) de cada fact
    * integridade referencial   as FKs apontam para linhas que existem
    * postback >= visita        nao se converte antes de clicar
    * coerencia de fonte        a traffic_source da conversao e a da sua campanha
    * reconciliacao             eventos e daily control somam o mesmo (exceto is_manual)

Nota: varias destas verificacoes ja sao garantidas por constraints (PK, FK).
Mesmo assim verificam-se: uma constraint e a primeira linha de defesa, o check
e a segunda - protege-te de quem alivie o schema (ex.: uma base noutro
servidor sem FKs) e da-te uma metrica auditavel.

A reconciliacao e o check que MAIS vale a pena: apanha o que nenhuma constraint
apanha, dois sistemas a discordar sobre o mesmo numero.

Fica DE FORA, de proposito, qualquer regra do tipo "conversions <= clicks": nao
e uma lei universal (um click pode gerar varias conversoes: aqui ate geramos
conversoes de tipo 2 para o mesmo click). Seria legitimo acrescenta-la como
regra especifica de um dataset onde se saiba que e verdade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg

from pipeline.config import get_settings
from pipeline.load import connect

log = logging.getLogger(__name__)


class QualityCheckFailed(Exception):
    """Pelo menos uma verificacao de qualidade falhou."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _scalar(conn: psycopg.Connection, query: str, params: tuple) -> Any:
    return conn.execute(query, params).fetchone()[0]


def run_checks(
    conn: psycopg.Connection, start: datetime, end: datetime, max_lag_hours: float,
    tolerance: float = 0.05,
) -> list[CheckResult]:
    w = (start, end)  # janela [start, end)
    d = (start.date(), end.date())  # dias [start, end) para o daily control
    results: list[CheckResult] = []

    def check(name: str, passed: bool, detail: str) -> None:
        results.append(CheckResult(name, passed, detail))

    # --- row count > 0 ------------------------------------------------------
    counts = {
        "fact_conversions": ("postback_timestamp", w),
        "fact_campaign_costs": ("datetime", w),
        "fact_daily_control": ("date", d),
    }
    for table, (col, params) in counts.items():
        n = _scalar(conn, f"SELECT count(*) FROM {table} WHERE {col} >= %s AND {col} < %s", params)
        check(f"{table}: row count > 0", n > 0, f"{n} linhas na janela")

    # --- freshness ----------------------------------------------------------
    latest = _scalar(conn, "SELECT max(datetime) FROM fact_campaign_costs WHERE datetime >= %s AND datetime < %s", w)
    threshold = end - timedelta(hours=max_lag_hours)
    check(
        "fact_campaign_costs: freshness",
        latest is not None and latest >= threshold,
        f"ultima hora de custo: {latest}; minimo aceitavel: {threshold}",
    )

    # --- chaves unicas (compostas) -----------------------------------------
    unique = {
        "fact_conversions": ("click_id, conversion_type_id, postback_timestamp", "postback_timestamp", w),
        "fact_campaign_costs": ("datetime, campaign_id, investment_provider", "datetime", w),
        "fact_daily_control": ("date, campaign_id", "date", d),
    }
    for table, (key, col, params) in unique.items():
        dup = _scalar(
            conn,
            f"SELECT count(*) FROM (SELECT 1 FROM {table} WHERE {col} >= %s AND {col} < %s "
            f"GROUP BY {key} HAVING count(*) > 1) x",
            params,
        )
        check(f"{table}: chave unica", dup == 0, f"{dup} chaves repetidas")

    # --- integridade referencial (anti-joins: linhas SEM correspondencia) ---
    fks = {
        "fact_conversions": ("postback_timestamp", w, [
            ("campaign_id", "dim_campaign"), ("traffic_source_id", "dim_traffic_source"), ("offer_id", "dim_offer")]),
        "fact_campaign_costs": ("datetime", w, [("campaign_id", "dim_campaign")]),
        "fact_daily_control": ("date", d, [("campaign_id", "dim_campaign")]),
    }
    for table, (col, params, refs) in fks.items():
        missing = " OR ".join(
            f"NOT EXISTS (SELECT 1 FROM {dim} d WHERE d.{fk} = f.{fk})" for fk, dim in refs
        )
        orphans = _scalar(
            conn, f"SELECT count(*) FROM {table} f WHERE f.{col} >= %s AND f.{col} < %s AND ({missing})", params
        )
        check(f"{table}: FKs validas", orphans == 0, f"{orphans} linhas com dimensao inexistente")

    # --- coerencia dentro da linha ------------------------------------------
    before = _scalar(
        conn,
        "SELECT count(*) FROM fact_conversions WHERE postback_timestamp >= %s AND postback_timestamp < %s "
        "AND postback_timestamp < visit_timestamp",
        w,
    )
    check("conversion.postback_timestamp >= visit_timestamp", before == 0, f"{before} conversoes antes da visita")

    # --- coerencia entre tabelas: fonte da conversao == fonte da campanha ----
    mismatch = _scalar(
        conn,
        """
        SELECT count(*) FROM fact_conversions f
        JOIN dim_campaign c USING (campaign_id)
        WHERE f.postback_timestamp >= %s AND f.postback_timestamp < %s
          AND f.traffic_source_id <> c.traffic_source_id
        """,
        w,
    )
    check("conversion.traffic_source == campaign.traffic_source", mismatch == 0, f"{mismatch} conversoes incoerentes")

    # --- reconciliacao: eventos vs daily control (dois sistemas) ------------
    bad = conn.execute(
        """
        SELECT count(*) FILTER (WHERE abs(revenue_diff) > %s) AS revenue_bad,
               count(*) FILTER (WHERE abs(investment_diff) > %s) AS investment_bad,
               count(*) AS compared
        FROM v_reconciliation_daily
        WHERE NOT is_manual AND date >= %s AND date < %s
        """,
        (tolerance, tolerance, *d),
    ).fetchone()
    check(
        "reconciliacao: revenue (eventos vs daily control)", bad[0] == 0,
        f"{bad[0]} de {bad[2]} campanha-dia (nao manuais) fora de +-{tolerance}",
    )
    check(
        "reconciliacao: investment (eventos vs daily control)", bad[1] == 0,
        f"{bad[1]} de {bad[2]} campanha-dia (nao manuais) fora de +-{tolerance}",
    )

    return results


def run_quality_check(load_meta: dict[str, Any]) -> dict[str, Any]:
    """Task `quality_check`: corre TODAS as verificacoes e falha se alguma falhar."""
    start = datetime.fromisoformat(load_meta["interval_start"])
    end = datetime.fromisoformat(load_meta["interval_end"])
    with connect() as conn:
        results = run_checks(conn, start, end, get_settings().freshness_max_lag_hours)

    for r in results:
        (log.info if r.passed else log.error)("%s  %s  (%s)", "PASS" if r.passed else "FAIL", r.name, r.detail)
    failed = [r for r in results if not r.passed]
    if failed:
        raise QualityCheckFailed(
            f"{len(failed)} de {len(results)} verificacoes falharam: " + "; ".join(r.name for r in failed)
        )
    return {**load_meta, "quality": {r.name: "pass" for r in results}}
