"""CLI do Controlled Business Agent.

    python app.py "Quanto gastamos ontem na Erobella?" -v
    python app.py "Qual provider teve maior CPC nos ultimos 7 dias?" --naive -v
    python app.py diagnose conversion_rate 2026-11-05 [--explain]
    python app.py dashboard
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal

from agent import run_agent
from config import get_settings
from observability import format_receipt


def cmd_ask(args) -> int:
    record = run_agent(args.question, naive=args.naive)
    if record["error"]:
        print(f"ERRO: {record['error']}", file=sys.stderr)
    else:
        print(record["answer"])
    if args.verbose:
        print("\n" + format_receipt(record))
    return 1 if record["error"] else 0


def cmd_diagnose(args) -> int:
    from workflows.diagnose_metric_drop import diagnose_metric_drop, explain, format_report

    result = diagnose_metric_drop(args.metric, date.fromisoformat(args.day), args.period_days)
    print(format_report(result))
    if args.explain and "error" not in result and result["direction"] != "no_change":
        print("\n" + explain(result))
    return 1 if "error" in result else 0


def cmd_dashboard(args) -> int:
    from dashboard.spec import EXAMPLE_SPEC, DashboardSpec, build_chart_queries
    from tools.postgres import execute

    spec = DashboardSpec.model_validate(json.load(open(args.spec)) if args.spec else EXAMPLE_SPEC)
    print(f"# {spec.title}")
    for chart, sql, params in build_chart_queries(spec):
        columns, rows = execute(sql, params)
        print(f"\n[{chart.type}] {chart.metric} by {chart.dimension}\n{sql}")
        for row in rows:
            print("  ", *(f"{v:.4f}" if isinstance(v, (Decimal, float)) else v for v in row))
    return 0


def main() -> int:
    get_settings()  # falha cedo se o .env estiver mal
    if len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        p = argparse.ArgumentParser(prog="app.py diagnose")
        p.add_argument("command"), p.add_argument("metric"), p.add_argument("day")
        p.add_argument("--period-days", type=int, default=1)
        p.add_argument("--explain", action="store_true", help="1 chamada ao LLM para redigir a explicacao")
        return cmd_diagnose(p.parse_args())
    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        p = argparse.ArgumentParser(prog="app.py dashboard")
        p.add_argument("command"), p.add_argument("spec", nargs="?", help="ficheiro JSON (default: exemplo)")
        return cmd_dashboard(p.parse_args())
    p = argparse.ArgumentParser(description="Controlled Business Agent")
    p.add_argument("question")
    p.add_argument("--naive", action="store_true", help="sem get_metric_definition")
    p.add_argument("-v", "--verbose", action="store_true", help="imprime o recibo do request")
    return cmd_ask(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
