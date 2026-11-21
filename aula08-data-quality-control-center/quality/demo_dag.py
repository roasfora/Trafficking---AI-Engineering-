"""Fallback executavel do DAG: o mesmo fluxo e os mesmos estados do Airflow, sem Airflow.

    python -m quality.demo_dag --scenario broken                  # strict (como no Airflow)
    python -m quality.demo_dag --scenario broken --gate-mode observe

    simulate_* -> load_bronze -> bronze_quality -> normalize -> silver_quality -> semantic_quality -> notify -> publish
"""

from __future__ import annotations

import argparse

from config import PROVIDERS
from quality.pipeline import RunContext, build_tasks, ensure_run, run_graph

ICON = {"success": "OK     ", "failed": "FAILED ", "upstream_failed": "SKIPPED"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=["healthy", "broken"], default="broken")
    ap.add_argument("--provider", action="append", choices=PROVIDERS)
    ap.add_argument("--gate-mode", choices=["strict", "observe"], default="strict")
    args = ap.parse_args(argv)

    lines: list[str] = []
    rc = RunContext.create(scenario=args.scenario, providers=tuple(args.provider or ()), gate_mode=args.gate_mode,
                           log=lines.append)
    ensure_run(rc)
    tasks = build_tasks()
    result = run_graph(rc, tasks)

    print(f"DAG provider_data_quality | run={rc.run_id} | scenario={args.scenario} | gate_mode={args.gate_mode}\n")
    group = None
    for t in tasks:
        if t.group != group:
            group = t.group
            print(f"[{group}]")
        extra = f"   <- {result.errors[t.id]}" if t.id in result.errors else ""
        print(f"   {t.id:18} {ICON[result.states[t.id]]}{extra}")
    print()
    for line in lines:
        print(line)
    print(f"\nresult: {'PUBLISHED' if result.published else 'BLOCKED: consumers keep the last good data'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
