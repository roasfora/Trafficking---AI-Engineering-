"""RECONCILE: os dados que guardamos batem certo com o que o provider diz?

    total de CONTROLO da API (independente do detalhe)
        vs
    SUM(cost) em PostgreSQL, para date + provider + currency

    provider=trafficjunky date=2026-10-20 currency=EUR
    api_total=1032.45 db_total=1032.45 difference=0.00 tolerance=0.01 status=PASS

Se a diferenca ultrapassar a tolerancia, a task FALHA.

Porque existe: tudo o resto pode correr sem erros e os dados estarem errados.
HTTP 200, contrato cumprido, transform sem excecoes, load com sucesso, e ainda
assim faltar custo (uma resposta truncada, campanhas descartadas por nao termos
correspondencia). Sucesso OPERACIONAL nao implica dados CORRETOS: a reconciliacao e
o que compara o resultado com uma fonte independente.

Nao implementado de proposito (comportamento de producao nos tickets reais):
* apagar o dia quando a base de dados tem MAIS do que a API;
* reprocessar em loop ate nao criar documentos novos (os relatorios mudam);
* alerta no Slack se ainda houver diferenca.

A moeda e parte da comparacao: custos de moedas diferentes nunca se somam.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pipeline.config import get_settings
from pipeline.load import connect

log = logging.getLogger(__name__)


class ReconciliationFailed(Exception):
    """O total na base de dados nao bate certo com o total da API."""


@dataclass(frozen=True)
class ReconciliationResult:
    provider: str
    date: date
    currency: str
    api_total: Decimal
    db_total: Decimal
    tolerance: Decimal

    @property
    def difference(self) -> Decimal:
        return self.api_total - self.db_total  # > 0: falta custo na base de dados

    @property
    def status(self) -> str:
        return "PASS" if abs(self.difference) <= self.tolerance else "FAIL"

    def log(self) -> None:
        line = (
            f"provider={self.provider} date={self.date} currency={self.currency}\n"
            f"    api_total={self.api_total:.2f}  db_total={self.db_total:.2f}  "
            f"difference={self.difference:.2f}  tolerance={self.tolerance}  status={self.status}"
        )
        (log.info if self.status == "PASS" else log.error)("reconciliacao\n    %s", line)


def db_total(conn, provider: str, day: date, currency: str) -> Decimal:
    return conn.execute(
        "SELECT COALESCE(SUM(cost), 0) FROM fact_campaign_daily "
        "WHERE date = %s AND provider = %s AND currency = %s",
        (day, provider, currency),
    ).fetchone()[0]


def run_reconcile(meta: dict[str, Any], api_total: Decimal, api_currency: str | None = None) -> dict[str, Any]:
    """Task `reconcile`. `api_total` vem da API (ver providers/*.fetch_api_total)."""
    settings = get_settings()
    day = date.fromisoformat(meta["date"])
    currency = meta["currency"]
    if api_currency is not None and api_currency != currency:
        raise ReconciliationFailed(
            f"{meta['provider']}: a API reporta {api_currency} mas a pipeline carrega {currency}; "
            "custos em moedas diferentes nao se comparam sem conversao"
        )
    with connect() as conn:
        total = db_total(conn, meta["provider"], day, currency)
    result = ReconciliationResult(meta["provider"], day, currency, Decimal(api_total), total,
                                  settings.reconcile_tolerance)
    result.log()
    if result.status == "FAIL":
        raise ReconciliationFailed(
            f"{result.provider} {result.date} {result.currency}: API={result.api_total:.2f} "
            f"DB={result.db_total:.2f} (diferenca {result.difference:.2f} > tolerancia {result.tolerance})"
        )
    return {**meta, "reconciliation": {"api_total": str(result.api_total), "db_total": str(result.db_total),
                                       "difference": str(result.difference), "status": result.status}}
