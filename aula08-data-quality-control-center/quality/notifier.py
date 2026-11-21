"""Alertas simulados. Interface unica: `notify(result)`.

ConsoleNotifier funciona sempre (e grava o alerta em data_quality.alerts).
WebhookNotifier e opcional: so existe se DQ_WEBHOOK_URL estiver definido; sem URL nunca toca na internet.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

from config import Settings, get_settings
from quality.models import CheckResult


def build_payload(result: CheckResult) -> dict[str, Any]:
    """O que viaja no webhook (e o que o alerta de consola resume)."""
    return {
        "provider": result.provider, "dataset": result.dataset, "layer": result.layer,
        "check": result.check_name, "status": result.status, "observed": result.observed_value,
        "expected": result.expected_value, "threshold": result.threshold, "run_id": result.run_id,
        "message": result.message,
    }


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{value:g}"


class ConsoleNotifier:
    """Imprime `[DQ ALERT] ...` e persiste o alerta (se tiver ligacao)."""

    def __init__(self, conn=None, stream=None):
        self.conn, self.stream = conn, stream or sys.stdout

    def notify(self, result: CheckResult) -> None:
        p = build_payload(result)
        print(f"[DQ ALERT] provider={p['provider']} layer={p['layer']} check={p['check']} status={p['status']} "
              f"observed={_fmt(p['observed'])} expected={_fmt(p['expected'])}", file=self.stream)
        if result.message:
            print(f"           {result.message}", file=self.stream)
        if self.conn is not None:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO data_quality.alerts (run_id, check_name, provider, status, message, sent_at, destination)
                       VALUES (%s, %s, %s, %s, %s, now(), 'console')""",
                    (result.run_id, result.check_name, result.provider, result.status, result.message),
                )
            self.conn.commit()


class WebhookNotifier:
    """POST JSON para DQ_WEBHOOK_URL. Uma falha de rede nunca derruba o pipeline."""

    def __init__(self, url: str, timeout: float = 5.0):
        self.url, self.timeout = url, timeout

    def notify(self, result: CheckResult) -> None:
        body = json.dumps(build_payload(result)).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(request, timeout=self.timeout).close()  # noqa: S310 (URL do operador)
        except Exception as exc:  # alerta falhado nao e razao para falhar o run
            print(f"[DQ ALERT] webhook delivery failed: {type(exc).__name__}", file=sys.stderr)


class MultiNotifier:
    def __init__(self, notifiers: list):
        self.notifiers = notifiers

    def notify(self, result: CheckResult) -> None:
        for n in self.notifiers:
            n.notify(result)


def get_notifier(conn=None, settings: Settings | None = None) -> MultiNotifier:
    settings = settings or get_settings()
    notifiers: list = [ConsoleNotifier(conn)]
    if settings.webhook_url:
        notifiers.append(WebhookNotifier(settings.webhook_url))
    return MultiNotifier(notifiers)
