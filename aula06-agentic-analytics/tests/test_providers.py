import io
import json
from dataclasses import replace

import pytest

import providers
from config import BEDROCK_MODEL_VARS, get_settings
from providers import bedrock_models, discover_ollama_models, get_llm, with_model


@pytest.fixture
def settings():
    return replace(get_settings(), bedrock_models={}, bedrock_model_id="", ollama_models=())


def test_bedrock_registry_ignores_empty_ids(monkeypatch):
    from config import _bedrock_models
    for var in BEDROCK_MODEL_VARS.values():
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("BEDROCK_NOVA_LITE_MODEL_ID", "id-nova-lite")
    monkeypatch.setenv("BEDROCK_GPT_TERRA_MODEL_ID", "  ")
    assert _bedrock_models() == {"Nova Lite": "id-nova-lite"}


def test_bedrock_models_includes_cli_default_once(settings):
    s = replace(settings, bedrock_models={"Nova Lite": "a"}, bedrock_model_id="b")
    assert bedrock_models(s) == {"Nova Lite": "a", "Default (BEDROCK_MODEL_ID)": "b"}
    assert bedrock_models(replace(s, bedrock_model_id="a")) == {"Nova Lite": "a"}


def test_ollama_provider_builds(settings):
    llm = get_llm("ollama", "qwen2.5:7b-instruct", settings)
    assert type(llm).__name__ == "ChatOllama" and llm.model == "qwen2.5:7b-instruct"


def test_bedrock_provider_builds_with_region_and_model(settings, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    llm = get_llm("bedrock", "some.model-id", replace(settings, aws_region="eu-north-1"))
    assert type(llm).__name__ == "ChatBedrockConverse"
    assert llm.model_id == "some.model-id" and llm.region_name == "eu-north-1"


def test_unknown_provider_rejected(settings):
    with pytest.raises(ValueError, match="unknown provider"):
        get_llm("openai", "gpt", settings)


def test_empty_model_rejected(settings):
    with pytest.raises(RuntimeError, match="not configured"):
        get_llm("bedrock", "", settings)


def test_with_model_switches_and_drops_foreign_prices(settings):
    s = replace(settings, llm_provider="bedrock", bedrock_model_id="m1", input_price_per_1m=1.0, output_price_per_1m=2.0)
    same = with_model(s, "bedrock", "m1")
    assert same.input_price_per_1m == 1.0
    other = with_model(s, "bedrock", "m2")
    assert (other.model_name, other.input_price_per_1m) == ("m2", None)
    oll = with_model(s, "ollama", "qwen")
    assert (oll.llm_provider, oll.model_name, oll.input_price_per_1m) == ("ollama", "qwen", None)


# --- descoberta do Ollama (HTTP simulado) ---------------------------------------
def fake_urlopen(body=None, exc=None):
    def _open(url, timeout):
        assert url.endswith("/api/tags")
        if exc:
            raise exc
        return io.BytesIO(body.encode())
    return _open


def test_discovery_returns_installed_models_without_embeddings(settings, monkeypatch):
    body = json.dumps({"models": [{"name": "qwen:7b"}, {"name": "nomic-embed-text:latest"}, {"name": "llama3:8b"}]})
    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen(body))
    assert discover_ollama_models(settings) == {"running": True, "models": ["qwen:7b", "llama3:8b"], "error": None}


def test_discovery_when_ollama_down_is_graceful(settings, monkeypatch):
    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen(exc=ConnectionRefusedError()))
    result = discover_ollama_models(settings)
    assert result["running"] is False and result["models"] == [] and "not running" in result["error"]


@pytest.mark.parametrize("body", ["not json", "{}", '{"models": [{"nome": "x"}]}', "[1, 2]"])
def test_discovery_malformed_response_is_graceful(settings, monkeypatch, body):
    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen(body))
    result = discover_ollama_models(replace(settings, ollama_models=("fallback:1b",)))
    assert result["models"] == ["fallback:1b"] and "Unexpected" in result["error"]


def test_bedrock_api_key_counts_as_credentials(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "dummy")
    assert providers.aws_credentials_found() is True
