"""VALIDATE: consumer-side contract validation.

Aqui o Pydantic faz de porteiro. Cada registo extraido e verificado contra o
MESMO contrato que a API diz cumprir (api/schemas.py). Se algum registo falhar,
a task falha e NADA do que vem a seguir corre.

O que esta task cobre (contrato):
    schema, campos obrigatorios, tipos, enums, constraints de campo
    (revenue >= 0, cost >= 0, country com 2 letras...)

O que NAO cobre (isso e a task `quality_check`, depois do load):
    contagens, freshness, chaves duplicadas, integridade referencial,
    coerencia entre campos (postback depois da visita) e entre sistemas
    (reconciliacao com o daily control)

Regra de bolso:
    Pydantic responde a "este REGISTO tem a forma certa?"
    Data quality responde a "este CONJUNTO de dados faz sentido?"

Evolucao de producao (fora do ambito desta versao): em vez de falhar tudo por
causa de uns poucos registos invalidos, enviar os invalidos para uma tabela de
quarentena e falhar so acima de um limiar.

Producer-side vs consumer-side:
    A API valida o que EMITE (so apanha bugs dela propria, e so se a validacao
    existir). A pipeline valida o que RECEBE. Se o producer mudar o formato
    sem avisar (modo `schema_drift`), apenas esta task o descobre.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from api.schemas import (
    Campaign,
    CampaignCost,
    Conversion,
    DailyControl,
    Offer,
    TrafficSource,
    Workspace,
)

log = logging.getLogger(__name__)

CONTRACTS: dict[str, type[BaseModel]] = {
    "workspaces": Workspace,
    "traffic_sources": TrafficSource,
    "campaigns": Campaign,
    "offers": Offer,
    "conversions": Conversion,
    "campaign_costs": CampaignCost,
    "daily_control": DailyControl,
}


class ContractViolation(Exception):
    """Os dados recebidos nao cumprem o contrato acordado com o producer."""


def validate_records(name: str, rows: list[dict[str, Any]]) -> Counter:
    """Valida TODOS os registos (nao pára no primeiro erro).

    Devolve um Counter {(campo, tipo_de_erro): numero_de_registos}. Ver todos
    os erros de uma vez diz-te se e um registo estragado ou o schema inteiro.
    """
    model = CONTRACTS[name]
    problems: Counter = Counter()
    invalid = 0
    for row in rows:
        try:
            model.model_validate(row)
        except ValidationError as exc:
            invalid += 1
            for err in exc.errors():
                field = ".".join(str(p) for p in err["loc"]) or "<registo>"
                problems[(field, err["type"])] += 1
    problems["__invalid_records__"] = invalid
    return problems


def run_validate(extract_meta: dict[str, Any]) -> dict[str, Any]:
    """Task `validate`. Falha com ContractViolation se algum dataset violar o contrato."""
    failures: list[str] = []
    validated: dict[str, int] = {}

    for name in CONTRACTS:
        rows = json.loads(Path(extract_meta["files"][name]).read_text())
        problems = validate_records(name, rows)
        invalid = problems.pop("__invalid_records__")
        if invalid == 0:
            log.info("%-16s %5d registos validos", name, len(rows))
            validated[name] = len(rows)
            continue

        log.error("%-16s %d de %d registos INVALIDOS", name, invalid, len(rows))
        for (field, kind), n in problems.most_common():
            log.error("    campo=%-18s erro=%-28s em %d registos", field, kind, n)
        top_field, top_kind = problems.most_common(1)[0][0]
        failures.append(f"{name}: {invalid}/{len(rows)} invalidos (ex.: {top_field} -> {top_kind})")

    if failures:
        raise ContractViolation(
            "Os dados recebidos violam o data contract. " + " | ".join(failures)
        )
    return {**extract_meta, "validated": validated}
