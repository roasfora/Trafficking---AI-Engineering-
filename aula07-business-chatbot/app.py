"""CLI do chatbot interno de negocio (Aula 07).

    python app.py "O que e CPC?" -v
    python app.py "Qual provider teve maior CPC ontem e como definimos CPC?" -v
"""

from __future__ import annotations

import argparse
import sys

from agent import run_agent
from config import get_settings
from observability import format_receipt


def main() -> int:
    get_settings()  # falha cedo se o .env estiver mal
    p = argparse.ArgumentParser(description="Business chatbot: RAG for knowledge, SQL for facts")
    p.add_argument("question")
    p.add_argument("-v", "--verbose", action="store_true", help="imprime o recibo do request")
    args = p.parse_args()

    record = run_agent(args.question)
    if record["error"]:
        print(f"ERRO: {record['error']}", file=sys.stderr)
    else:
        print(record["answer"])
    if args.verbose:
        print("\n" + format_receipt(record))
    return 1 if record["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
