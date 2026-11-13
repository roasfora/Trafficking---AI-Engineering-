"""evals/questions.yaml: estrutura valida e, para perguntas de dados, o SQL de referencia bate certo com o PostgreSQL."""

from pathlib import Path

import pytest
import yaml

from agent import ALL_TOOLS
from tools.postgres import execute
from tools.sql_guard import check_sql

QUESTIONS = yaml.safe_load((Path(__file__).resolve().parent.parent / "evals" / "questions.yaml").read_text())["questions"]
TOOL_NAMES = {t.name for t in ALL_TOOLS}


def test_at_least_twelve_questions_in_three_categories():
    assert len(QUESTIONS) >= 12
    assert {q["category"] for q in QUESTIONS} == {"knowledge", "data", "mixed"}
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)


def test_expected_tools_exist_and_follow_the_golden_rule():
    for q in QUESTIONS:
        assert set(q.get("expected_tools", [])) <= TOOL_NAMES, q["id"]
        if q["category"] == "knowledge":
            assert q["expected_tools"] == ["search_internal_knowledge"], q["id"]  # conhecimento nunca vai a SQL
        if q["category"] == "data":
            assert "run_postgres_query" in q["expected_tools"], q["id"]
            assert "search_internal_knowledge" not in q["expected_tools"], q["id"]  # factos nunca vem do RAG


def test_expected_sources_and_metrics_exist():
    from rag.index import DOC_TYPES
    from tools.metrics import load_semantic

    for q in QUESTIONS:
        source = q.get("expected_source")
        if source:
            assert source.split("#")[0] in set(DOC_TYPES) | {"semantic.yaml"}, q["id"]
        if q.get("expected_metric"):
            assert q["expected_metric"] in load_semantic()["metrics"], q["id"]


@pytest.mark.usefixtures("pg")
@pytest.mark.parametrize("q", [q for q in QUESTIONS if "expected_sql_result" in q], ids=lambda q: q["id"])
def test_reference_sql_matches_expected_rows(q):
    sql = " ".join(q["expected_sql_result"]["sql"].split())
    columns, rows = execute(check_sql(sql))  # o SQL de referencia passa pelo mesmo guard
    got = [[float(v) if hasattr(v, "as_tuple") else v for v in row] for row in rows]
    assert got == q["expected_sql_result"]["rows"]
