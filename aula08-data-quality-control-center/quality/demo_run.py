"""Corre o pipeline completo num cenario e mostra o resultado das quality gates.

    python -m quality.demo_run --scenario healthy
    python -m quality.demo_run --scenario broken
    python -m quality.demo_run --scenario broken --provider voluum --gate-mode strict
"""

from __future__ import annotations

import argparse

from config import PROVIDERS, get_settings
from db import connect
from quality.pipeline import RunContext, ensure_run, run_graph


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=["healthy", "broken"], default=settings.scenario)
    ap.add_argument("--provider", action="append", choices=PROVIDERS, help="repetir para varios; omitido = todos")
    ap.add_argument("--gate-mode", choices=["strict", "observe"], default=settings.gate_mode,
                    help="strict: um FAIL para o pipeline | observe: continua para mostrar todos os problemas")
    args = ap.parse_args(argv)

    rc = RunContext.create(scenario=args.scenario, providers=tuple(args.provider or ()), gate_mode=args.gate_mode)
    print(f"RUN {rc.run_id} | scenario={rc.scenario.name} | providers={','.join(rc.scenario.providers)} | gate_mode={rc.gate_mode}\n")
    ensure_run(rc)
    result = run_graph(rc)

    print("\n--- issues (WARN / FAIL) ---")
    with connect(settings) as conn:
        rows = conn.execute("""SELECT status, provider, layer, check_name, details ->> 'message' AS message
                               FROM data_quality.check_results WHERE run_id = %s AND status <> 'PASS'
                               ORDER BY status DESC, provider, layer, check_name""", (rc.run_id,)).fetchall()
    for r in rows:
        print(f"{r['status']:4} {r['provider']:12} {r['layer']:8} {r['check_name']:38} {r['message']}")
    if not rows:
        print("none: every check passed")

    print("\n--- summary ---")
    for layer in ("bronze", "silver", "semantic"):
        print(f"{layer.upper():9} GATE: {result.gates.get(layer, 'NOT RUN')}")
    print(f"PUBLISH: {'ALLOWED' if result.published else 'BLOCKED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
