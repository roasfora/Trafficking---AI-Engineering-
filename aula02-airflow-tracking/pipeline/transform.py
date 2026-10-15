"""TRANSFORM: Python + Pandas, sem abstracoes.

Os dados chegaram e cumprem o contrato. Agora preparamo-los para o destino:

    * normalizar timestamps (tudo em UTC, com timezone)
    * normalizar strings (espacos, maiusculas/minusculas)
    * calcular campos simples (visit_date, cost_date)
    * garantir tipos (inteiros que podem ser nulos, booleanos, decimais)
    * remover duplicados (pela CHAVE de cada tabela)

O que NAO fazemos aqui: calcular CPC, CTR, ROAS, profit... Metricas derivadas
nao se guardam por linha (ver sql/analytics.sql).

Cada dataset tem uma especificacao (SPECS) que diz que colunas tem, qual a
chave, e que limpeza se aplica. A logica e uma so: ler a especificacao e
aplica-la.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Spec:
    columns: list[str]  # colunas de DESTINO, pela ordem da tabela
    key: list[str]  # chave primaria (pode ser composta)
    text: list[str] = field(default_factory=list)  # strip
    lower: list[str] = field(default_factory=list)  # strip + minusculas
    upper: list[str] = field(default_factory=list)  # strip + maiusculas
    timestamps: list[str] = field(default_factory=list)  # -> datetime64[UTC]
    dates: list[str] = field(default_factory=list)  # -> date
    ints: list[str] = field(default_factory=list)  # -> Int64 (aceita nulos)
    floats: list[str] = field(default_factory=list)  # -> float64
    bools: list[str] = field(default_factory=list)
    decimals: int = 4  # casas decimais dos floats
    derived: dict[str, str] = field(default_factory=dict)  # coluna calculada -> coluna de origem


SPECS: dict[str, Spec] = {
    "workspaces": Spec(
        columns=["workspace_id", "name"], key=["workspace_id"],
        text=["workspace_id", "name"],
    ),
    "traffic_sources": Spec(
        columns=["traffic_source_id", "name", "currency_code", "deleted"], key=["traffic_source_id"],
        text=["traffic_source_id", "name"], upper=["currency_code"], bools=["deleted"],
    ),
    "campaigns": Spec(
        columns=["campaign_id", "name", "geo", "traffic_source_id", "workspace_id", "is_paused", "created"],
        key=["campaign_id"],
        text=["campaign_id", "name", "traffic_source_id", "workspace_id"], upper=["geo"],
        timestamps=["created"], bools=["is_paused"],
    ),
    "offers": Spec(
        columns=["offer_id", "name", "country_code", "affiliate_network_id", "affiliate_network_name",
                 "payout", "currency_code", "deleted"],
        key=["offer_id"],
        text=["offer_id", "name", "affiliate_network_id", "affiliate_network_name"],
        upper=["country_code", "currency_code"], floats=["payout"], bools=["deleted"],
    ),
    "conversions": Spec(
        columns=["click_id", "conversion_type_id", "postback_timestamp", "visit_timestamp", "visit_date",
                 "campaign_id", "traffic_source_id", "offer_id", "country_code",
                 "revenue", "revenue_original_currency"],
        key=["click_id", "conversion_type_id", "postback_timestamp"],
        text=["click_id", "campaign_id", "traffic_source_id", "offer_id"], upper=["country_code"],
        timestamps=["postback_timestamp", "visit_timestamp"], dates=["visit_date"],
        ints=["conversion_type_id"], floats=["revenue", "revenue_original_currency"],
        derived={"visit_date": "visit_timestamp"},
    ),
    "campaign_costs": Spec(
        columns=["datetime", "cost_date", "campaign_id", "investment_provider", "cost", "clicks", "impressions"],
        key=["datetime", "campaign_id", "investment_provider"],
        text=["campaign_id"], lower=["investment_provider"],
        timestamps=["datetime"], dates=["cost_date"], ints=["clicks", "impressions"], floats=["cost"],
        derived={"cost_date": "datetime"},
    ),
    "daily_control": Spec(
        columns=["date", "campaign_id", "revenue", "investment", "is_manual"], key=["date", "campaign_id"],
        text=["campaign_id"], dates=["date"], floats=["revenue", "investment"], bools=["is_manual"],
        decimals=2,  # o daily control vem arredondado a 2 casas
    ),
}
FACTS = ["conversions", "campaign_costs", "daily_control"]
KEYS = {name: spec.key for name, spec in SPECS.items()}  # usado pelo load


def transform(name: str, rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Aplica a especificacao de `name` a uma lista de registos (JSON)."""
    spec = SPECS[name]
    source_columns = [c for c in spec.columns if c not in spec.derived]
    df = pd.DataFrame.from_records(rows, columns=source_columns)

    # 1. timestamps: tudo para UTC com timezone (ISO 8601 -> datetime64[UTC])
    for col in spec.timestamps:
        df[col] = pd.to_datetime(df[col], utc=True)
    # 2. datas: as vindas da API ("2026-10-01") e as calculadas a partir de um timestamp
    for col in spec.dates:
        df[col] = (df[spec.derived[col]].dt.date if col in spec.derived
                   else pd.to_datetime(df[col]).dt.date)
    # 3. strings limpas (uma string vazia passa a NULL)
    for col in spec.text + spec.lower + spec.upper:
        if col in df:
            cleaned = df[col].astype("object").str.strip()
            if col in spec.lower:
                cleaned = cleaned.str.lower()
            if col in spec.upper:
                cleaned = cleaned.str.upper()
            df[col] = cleaned.replace("", None)
    # 4. tipos garantidos
    for col in spec.ints:
        df[col] = df[col].astype("Int64")  # inteiro que aceita NULL (int64 normal nao aceita)
    for col in spec.floats:
        df[col] = df[col].astype("float64").round(spec.decimals)
    for col in spec.bools:
        df[col] = df[col].astype("bool")
    # 5. duplicados: o mesmo registo repetido (ex.: paginas sobrepostas) conta uma vez
    df = df.drop_duplicates(subset=spec.key, keep="last")
    return df[spec.columns].sort_values(spec.key).reset_index(drop=True)


# --------------------------------------------------------------------------
# I/O entre tasks
# --------------------------------------------------------------------------

def read_transformed(path: str | Path, name: str) -> pd.DataFrame:
    """Le um CSV transformado reconstruindo os tipos (CSV nao guarda tipos).

    * dtype=str nas colunas de texto: um ID como "000123" ou 32 digitos nao
      pode virar numero.
    * keep_default_na=False: sem isto o pandas le o pais "NA" (Namibia) como
      valor em falta. So a string vazia e NULL.
    """
    spec = SPECS[name]
    strings = {c: str for c in spec.text + spec.lower + spec.upper}
    df = pd.read_csv(path, keep_default_na=False, na_values=[""], dtype=strings)
    for col in spec.timestamps:
        df[col] = pd.to_datetime(df[col], utc=True)
    for col in spec.dates:
        df[col] = pd.to_datetime(df[col]).dt.date
    for col in spec.ints:
        df[col] = df[col].astype("Int64")
    for col in spec.floats:
        df[col] = df[col].astype("float64")
    for col in spec.bools:
        df[col] = df[col].astype("bool")
    return df[spec.columns]


def run_transform(validate_meta: dict[str, Any]) -> dict[str, Any]:
    """Task `transform`: raw_*.json -> transformed_*.csv. Devolve so metadados."""
    run_dir = Path(validate_meta["run_dir"])
    files: dict[str, str] = {}
    counts: dict[str, int] = {}

    for name in SPECS:
        rows = json.loads(Path(validate_meta["files"][name]).read_text())
        df = transform(name, rows)
        dropped = len(rows) - len(df)
        target = run_dir / f"transformed_{name}.csv"
        df.to_csv(target, index=False)
        files[name] = str(target)
        counts[name] = len(df)
        log.info("%-16s %5d -> %5d linhas (%d duplicados removidos)", name, len(rows), len(df), dropped)

    return {
        "run_dir": str(run_dir),
        "interval_start": validate_meta["interval_start"],
        "interval_end": validate_meta["interval_end"],
        "files": files,
        "counts": counts,
    }
