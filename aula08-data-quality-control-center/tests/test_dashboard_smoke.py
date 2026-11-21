"""O dashboard le a qualidade, nao a define."""

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent / "dashboard" / "streamlit_app.py"


def _imports(tree) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_dashboard_source_does_not_define_quality():
    src = APP.read_text(encoding="utf-8")
    assert "data_quality.check_results" in src                       # a unica fonte dos estados
    for forbidden in ("warn_pct", "fail_pct", "max_delay_hours", "rolling_mean_change", "z_score"):
        assert forbidden not in src                                  # nenhum limite vive no dashboard
    imported_quality = {m for m in _imports(ast.parse(src)) if m.startswith("quality")}
    assert imported_quality == {"quality.pipeline"}                  # so o botao "Run scenario": nenhum check importado


def test_dashboard_sql_is_read_only():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    queries = {n.targets[0].id: n.value.value for n in tree.body
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id.endswith("_SQL")}
    assert set(queries) == {"RESULTS_SQL", "RUNS_SQL", "API_RUNS_SQL"}
    assert all(q.lstrip().upper().startswith("SELECT") for q in queries.values())
    assert any("data_quality.check_results" in q for q in queries.values())


def test_dashboard_renders_healthy_and_broken_runs(healthy_run, broken_run):
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Data Quality Control Center"
    assert any("Bronze → Silver → Gold" in c.value for c in at.caption)
    assert [b.label for b in at.sidebar.button] == ["Run healthy scenario", "Run broken scenario"]

    at.sidebar.selectbox(key="run_select").select(broken_run.run_id).run()      # valor bruto = run_id
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "BLOCKED" in html and "Critical failures" in html and "Publish status" in html
    assert all(name in html for name in ("Erobella", "TrafficJunky", "Voluum"))
    assert "RED" in html                                             # providers com FAIL
    assert {"Latest failing checks", "Drill-down"} <= {s.value for s in at.subheader}
    assert any("Why it matters" in m.value for m in at.markdown)     # drill-down do primeiro check falhado


def test_dashboard_healthy_run_has_nothing_failing(healthy_run, broken_run):
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.selectbox(key="run_select").select(healthy_run.run_id).run()
    assert not at.exception
    assert any("No WARN or FAIL" in s.value for s in at.success)
    assert "PUBLISHED" in " ".join(m.value for m in at.markdown)
