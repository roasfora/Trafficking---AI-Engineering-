"""RAG: documentos de metricas, indexacao (chunks) e tool de conhecimento.

Os testes sem DB usam embeddings falsos (FakeEmbeddings): nao precisam de Ollama nem de PostgreSQL.
Os testes de integracao (marcados com `rag`) precisam do indice criado com `python -m rag.index`.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from rag.index import DOC_TYPES, KNOWLEDGE_DIR, load_markdown_documents, split_documents
from rag.metric_documents import metric_documents
from tools.knowledge import search_internal_knowledge, source_label
from tools.metrics import get_metric_definition, load_semantic, one_line


def test_one_metric_document_per_semantic_metric():
    docs = metric_documents()
    assert [d.metadata["metric"] for d in docs] == list(load_semantic()["metrics"])
    assert all(d.metadata["source"] == "semantic.yaml" for d in docs)
    assert all(d.metadata["doc_type"] == "metric_definition" for d in docs)


def test_metric_document_formula_is_the_semantic_yaml_formula():
    """Uma fonte de verdade: o RAG e a tool get_metric_definition dizem o mesmo."""
    by_metric = {d.metadata["metric"]: d for d in metric_documents()}
    for key, metric in load_semantic()["metrics"].items():
        assert one_line(metric["expression"]) in by_metric[key].page_content
        assert get_metric_definition(key)["expression"] in by_metric[key].page_content


def test_cpc_document_is_ratio_of_sums_and_forbids_averages():
    text = next(d for d in metric_documents() if d.metadata["metric"] == "cpc").page_content
    assert "SUM(cost) / NULLIF(SUM(clicks), 0)" in text
    assert "AVG(cpc)" in text and "Never compute it as" in text


def test_semantic_ratios_are_ratio_of_sums_never_average_of_ratios():
    for key in ("cpc", "ctr", "conversion_rate", "cpa", "roas", "roi"):
        expr = one_line(load_semantic()["metrics"][key]["expression"])
        assert expr.count("SUM(") >= 2 and "AVG(" not in expr, key


def test_semantic_has_all_requested_metrics():
    expected = {"spend", "impressions", "visits", "clicks", "conversions", "revenue",
                "cpc", "ctr", "conversion_rate", "cpa", "roas", "profit", "roi"}
    assert expected <= set(load_semantic()["metrics"])


def test_markdown_documents_carry_source_and_doc_type():
    docs = load_markdown_documents()
    assert {d.metadata["source"] for d in docs} == set(DOC_TYPES)
    assert {p.name for p in KNOWLEDGE_DIR.glob("*.md")} == set(DOC_TYPES)
    assert next(d for d in docs if d.metadata["source"] == "provider_notes.md").metadata["doc_type"] == "provider_note"


def test_split_keeps_metadata_and_respects_chunk_size():
    chunks = split_documents(load_markdown_documents() + metric_documents())
    assert len(chunks) > len(load_markdown_documents())
    assert all(len(c.page_content) <= 800 for c in chunks)
    assert all("source" in c.metadata and "doc_type" in c.metadata for c in chunks)
    assert {c.metadata["metric"] for c in chunks if "metric" in c.metadata} == set(load_semantic()["metrics"])


def test_source_label_for_metric_and_file():
    assert source_label({"source": "semantic.yaml", "metric": "cpc"}) == "semantic.yaml#cpc"
    assert source_label({"source": "provider_notes.md"}) == "provider_notes.md"


def test_knowledge_tool_returns_text_source_doc_type_score(monkeypatch):
    import tools.knowledge as knowledge

    doc = Document(page_content="price_eur depends on model", metadata={"source": "provider_notes.md", "doc_type": "provider_note"})
    monkeypatch.setattr(knowledge, "search", lambda query: [(doc, 0.2081)])
    assert search_internal_knowledge("price_eur") == {
        "results": [{"text": "price_eur depends on model", "source": "provider_notes.md",
                     "doc_type": "provider_note", "score": 0.2081}]
    }


def test_knowledge_tool_says_when_nothing_is_relevant(monkeypatch):
    import tools.knowledge as knowledge

    monkeypatch.setattr(knowledge, "search", lambda query: [])
    result = search_internal_knowledge("receita de pizza")
    assert result["results"] == [] and "No relevant" in result["note"]


def test_knowledge_tool_failure_is_an_error_not_an_exception(monkeypatch):
    import tools.knowledge as knowledge

    def boom(query):
        raise ConnectionError("ollama down")

    monkeypatch.setattr(knowledge, "search", boom)
    assert "Knowledge search unavailable" in search_internal_knowledge("x")["error"]


def test_knowledge_tool_never_touches_analytics_data():
    """Garantia estrutural: o modulo so importa o retriever (vector store), nunca o acesso a analytics/raw."""
    import ast
    import inspect

    import tools.knowledge as knowledge

    tree = ast.parse(inspect.getsource(knowledge))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported == {"__future__", "typing", "rag.retriever"}  # nada de tools.postgres / psycopg
    assert "execute" not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def test_max_distance_filters_far_chunks(monkeypatch):
    from dataclasses import replace

    import rag.retriever as retriever
    from config import get_settings

    near, far = Document(page_content="near"), Document(page_content="far")

    class Store:
        def similarity_search_with_score(self, query, k):
            return [(near, 0.30), (far, 0.45)]

    s = replace(get_settings(), knowledge_max_distance=0.40)
    assert retriever.search("q", settings=s, store=Store()) == [(near, 0.30)]
    s = replace(get_settings(), knowledge_max_distance=None)
    assert len(retriever.search("q", settings=s, store=Store())) == 2


# ------------------------------------------------------ integracao: precisa do indice
def test_retriever_returns_sources_and_scores(index_ready):
    from rag.retriever import search

    hits = search("O que significa price_eur na Erobella?")
    assert hits and hits[0][0].metadata["source"] == "provider_notes.md"
    assert all(isinstance(score, float) for _, score in hits)
    assert [s for _, s in hits] == sorted(s for _, s in hits)  # mais proximo primeiro


def test_source_metadata_is_preserved_in_the_vector_store(index_ready):
    from rag.retriever import search

    docs = [d for d, _ in search("O que e CPC?", k=8)]
    assert all("source" in d.metadata and "doc_type" in d.metadata for d in docs)
    assert any(d.metadata.get("metric") == "cpc" for d in docs)  # chunk gerado do semantic.yaml


def test_get_retriever_is_a_standard_langchain_retriever(index_ready):
    from rag.retriever import get_retriever

    docs = get_retriever(k=3).invoke("attribution window")
    assert 0 < len(docs) <= 3
    assert any(d.metadata["source"] == "attribution_policy.md" for d in docs)


def test_irrelevant_question_finds_nothing(index_ready):
    assert search_internal_knowledge("Qual a receita de pizza com chouriço?")["results"] == []
