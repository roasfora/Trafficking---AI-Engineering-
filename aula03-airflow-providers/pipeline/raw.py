"""Ficheiros em disco: as respostas RAW e os ficheiros intermedios.

    data/raw/<provider>/date=YYYY-MM-DD/response.json      o que a API devolveu
    data/staging/<provider>/date=YYYY-MM-DD/canonical.json o que o transform produziu

Duas regras:

1. As tasks NAO trocam datasets pelo XCom. O XCom vive na base de dados de
   metadados do Airflow e serve para mensagens pequenas. Os dados vao para
   ficheiros e o que viaja e o CAMINHO.

2. A pasta e determinada pelo DIA, nao pela hora a que a run arrancou: voltar a
   correr o mesmo dia reescreve os mesmos ficheiros, nunca acumula lixo.

O raw NAO e uma "camada bronze": e so a resposta tal como chegou, guardada para
poder inspecionar um erro ou reprocessar sem voltar a chamar a API.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.config import Settings


def raw_path(settings: Settings, provider: str, day: date) -> Path:
    return settings.raw_dir / provider / f"date={day.isoformat()}" / "response.json"


def staging_path(settings: Settings, provider: str, day: date) -> Path:
    return settings.staging_dir / provider / f"date={day.isoformat()}" / "canonical.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)  # nunca fica um ficheiro a meio


def save_raw(path: Path, page_bodies: list[str]) -> None:
    """Guarda as respostas EXATAMENTE como chegaram (os bytes de cada pagina).

    O ficheiro e um JSON valido {"pages": [<pagina 1>, <pagina 2>, ...]}, mas cada
    pagina e inserida como texto, sem passar por json.loads/dumps: assim nao se
    perdem formatos (12.30 continua a ser 12.30, nao 12.3).
    """
    _atomic_write(path, '{"pages": [' + ",".join(page_bodies) + "]}")


def save_json(path: Path, obj: Any) -> None:
    """Guarda um objeto; Decimal, date e UUID passam a texto (sem perder precisao)."""
    _atomic_write(path, json.dumps(obj, default=str, indent=1))
