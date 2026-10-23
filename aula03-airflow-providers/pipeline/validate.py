"""VALIDATE: duas validacoes, dois significados.

    validate_source      o payload do PROVIDER tem a forma esperada?
                         (campo obrigatorio em falta, tipo errado, campo renomeado)
                         -> FALHA a task: o contrato estrutural esta quebrado.

    validate_canonical   o registo transformado respeita o NOSSO modelo?
                         -> FALHA a task: se isto falha, ou o transform tem um bug,
                            ou o provider enviou valores impossiveis (ex.: custo negativo).

O que NAO se valida aqui e o que o transform rejeita linha a linha: uma campanha
sem correspondencia no nosso dominio e um dado semanticamente VALIDO mas que nao
sabemos mapear. Essas linhas sao descartadas e registadas no transform; a task
`reconcile` revela depois o impacto dessa perda.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from contracts.canonical import CampaignDailyStat

log = logging.getLogger(__name__)


class ContractViolation(Exception):
    """Os dados nao cumprem o contrato esperado."""


def read_json(path: str | Path) -> Any:
    """Le JSON com decimais EXATOS (nunca passam por float)."""
    return json.loads(Path(path).read_text(), parse_float=Decimal)


def validate_payload(model: type[BaseModel], payload: Any, label: str) -> BaseModel:
    """Valida TODO o payload (nao para no primeiro erro) e resume os problemas.

    O resumo agrupa por (campo, tipo de erro): ver 'revenue em falta em 40
    registos' diz-te se e uma linha estragada ou o schema inteiro.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        problems: Counter = Counter()
        for err in exc.errors():
            path = ".".join("*" if isinstance(p, int) else str(p) for p in err["loc"])
            problems[(path, err["type"])] += 1
        log.error("%s: contrato violado (%d erros)", label, sum(problems.values()))
        for (path, kind), n in problems.most_common():
            log.error("    campo=%-32s erro=%-24s em %d locais", path, kind, n)
        top_path, top_kind = problems.most_common(1)[0][0]
        raise ContractViolation(
            f"{label}: o payload viola o contrato ({sum(problems.values())} erros; "
            f"ex.: {top_path} -> {top_kind})"
        ) from None


def validate_canonical(meta: dict[str, Any]) -> dict[str, Any]:
    """Task `validate_canonical`: cada linha do staging cumpre CampaignDailyStat."""
    rows = read_json(meta["staging_path"])
    invalid = 0
    problems: Counter = Counter()
    for row in rows:
        try:
            CampaignDailyStat.model_validate(row)
        except ValidationError as exc:
            invalid += 1
            for err in exc.errors():
                problems[(".".join(str(p) for p in err["loc"]), err["type"])] += 1
    if invalid:
        for (field, kind), n in problems.most_common():
            log.error("    campo=%-20s erro=%-28s em %d linhas", field, kind, n)
        raise ContractViolation(
            f"{meta['provider']}: {invalid} de {len(rows)} linhas violam o modelo canonico"
        )
    log.info("%s: %d linhas validas no modelo canonico", meta["provider"], len(rows))
    return {**meta, "canonical_valid": len(rows)}
