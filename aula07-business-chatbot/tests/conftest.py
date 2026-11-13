import pytest

from config import get_settings
from tools.postgres import connect


@pytest.fixture(scope="session")
def pg():
    """Testes de integracao: precisam de `docker compose up -d`. Sem DB => skipped."""
    try:
        connect(get_settings()).close()
    except Exception as exc:
        pytest.skip(f"PostgreSQL local indisponivel: {exc}")


@pytest.fixture(scope="session")
def index_ready(pg):
    """Testes de RAG: precisam do indice (python -m rag.index) e do Ollama com nomic-embed-text."""
    from rag.retriever import search

    try:
        hits = search("CPC")
    except Exception as exc:
        pytest.skip(f"Indice RAG indisponivel (ollama pull nomic-embed-text; python -m rag.index): {exc}")
    if not hits:
        pytest.skip("Indice vazio: corre python -m rag.index")
