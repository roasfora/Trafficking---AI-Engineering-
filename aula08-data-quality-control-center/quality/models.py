"""Modelos do sistema de qualidade. Todos os checks devolvem `CheckResult`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Status = Literal["PASS", "WARN", "FAIL"]
ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}


def worst(statuses) -> str:
    """O pior estado de uma coleccao (vazia = PASS)."""
    return max(statuses, key=ORDER.__getitem__, default="PASS")


@dataclass
class CheckResult:
    run_id: str
    checked_at: datetime
    provider: str
    dataset: str
    layer: str
    check_name: str
    dimension: str
    status: Status
    observed_value: float | None = None
    expected_value: float | None = None
    threshold: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "checked_at": self.checked_at, "provider": self.provider,
            "dataset": self.dataset, "layer": self.layer, "check_name": self.check_name,
            "dimension": self.dimension, "status": self.status, "observed_value": self.observed_value,
            "expected_value": self.expected_value, "threshold": self.threshold, "details": self.details,
        }

    @property
    def message(self) -> str:
        return str(self.details.get("message", ""))


@dataclass
class GateResult:
    """Resultado de uma quality gate (uma camada). FAIL bloqueia o publish; WARN avisa mas deixa passar."""

    layer: str
    run_id: str
    provider: str
    status: Status
    publish_allowed: bool
    results: list[CheckResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {s: sum(1 for r in self.results if r.status == s) for s in ORDER}


def status_from_abs_pct(diff_pct: float, warn_pct: float | None, fail_pct: float | None) -> str:
    """`diff_pct` em valor absoluto: > fail_pct -> FAIL; > warn_pct -> WARN; senao PASS."""
    if fail_pct is not None and diff_pct > fail_pct:
        return "FAIL"
    if warn_pct is not None and diff_pct > warn_pct:
        return "WARN"
    return "PASS"


def pct_diff(observed: float, expected: float) -> float:
    """(observed - expected) / expected * 100. Se expected = 0: 0 quando iguais, 100 caso contrario."""
    if expected == 0:
        return 0.0 if observed == 0 else 100.0
    return (observed - expected) / abs(expected) * 100.0
