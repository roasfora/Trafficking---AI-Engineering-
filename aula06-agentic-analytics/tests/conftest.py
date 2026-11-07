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
