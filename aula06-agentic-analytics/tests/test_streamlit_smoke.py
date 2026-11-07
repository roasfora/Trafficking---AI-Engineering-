"""Smoke test: a pagina renderiza sem excecoes mesmo sem Bedrock configurado e com Ollama em baixo."""

from streamlit.testing.v1 import AppTest


def test_app_renders_without_providers(monkeypatch):
    for var in ("BEDROCK_NOVA2_LITE_MODEL_ID", "BEDROCK_NOVA_LITE_MODEL_ID", "BEDROCK_CLAUDE_HAIKU_MODEL_ID",
                "BEDROCK_GPT_TERRA_MODEL_ID", "BEDROCK_MODEL_ID"):
        monkeypatch.setenv(var, "")
    app = AppTest.from_file("../streamlit_app.py", default_timeout=20).run()
    assert not app.exception
    assert app.title[0].value == "Business Analytics Chatbot"
    assert any("not configured" in w.value for w in app.warning)
