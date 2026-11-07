from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import chat
from agent import history_to_messages, run_agent
from config import get_settings
from test_agent import FakeLLM  # noqa: E402  (mesmo diretorio de testes)


def ok(answer="resposta"):
    return {"answer": answer, "error": None, "stopped_by": "end_turn"}


def test_history_formatting_skips_notices_and_failures():
    messages = []
    chat.add_exchange(messages, "Q1", ok("A1"))
    chat.add_model_change(messages, "Ollama / qwen")
    chat.add_exchange(messages, "Q2", {"answer": None, "error": "RuntimeError: boom", "stopped_by": "error"})
    assert chat.history_for_agent(messages) == [
        {"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ]
    assert messages[2]["content"] == "Model changed to Ollama / qwen"


def test_clear_history_only_empties_messages():
    messages = []
    chat.add_exchange(messages, "Q", ok())
    chat.clear(messages)
    assert messages == []


def test_history_reaches_the_model_between_system_and_question(tmp_path):
    s = replace(get_settings(), log_path=tmp_path / "r.jsonl", bedrock_model_id="fake")
    llm = FakeLLM([AIMessage(content="menor: erobella")])
    history = [{"role": "user", "content": "Qual provider teve maior CPC?"},
               {"role": "assistant", "content": "TrafficJunky"}]
    run_agent("E qual teve menor?", s, llm=llm, history=history)
    sent = llm.seen_messages[0]
    assert [type(m) for m in sent] == [SystemMessage, HumanMessage, AIMessage, HumanMessage]
    assert sent[-1].content == "E qual teve menor?" and sent[1].content.startswith("Qual provider")


def test_history_is_capped():
    many = [{"role": "user", "content": str(i)} for i in range(50)]
    assert len(history_to_messages(many)) == 10 and history_to_messages(many)[-1].content == "49"


def test_selected_provider_and_model_reach_get_llm_and_receipt(tmp_path, monkeypatch):
    import agent
    seen = {}

    def fake_get_llm(provider, model_id, settings):
        seen.update(provider=provider, model_id=model_id)
        return FakeLLM([AIMessage(content="ok")])

    monkeypatch.setattr(agent, "get_llm", fake_get_llm)
    s = replace(get_settings(), log_path=tmp_path / "r.jsonl", llm_provider="bedrock", bedrock_model_id="cli-model")
    record = run_agent("x", s, provider="ollama", model_id="qwen2.5:7b-instruct")
    assert seen == {"provider": "ollama", "model_id": "qwen2.5:7b-instruct"}
    assert (record["provider"], record["model"]) == ("ollama", "qwen2.5:7b-instruct")


def test_same_tools_for_every_provider(tmp_path):
    s = replace(get_settings(), log_path=tmp_path / "r.jsonl")
    bound = []
    for provider in ("bedrock", "ollama"):
        llm = FakeLLM([AIMessage(content="ok")])
        run_agent("x", s, llm=llm, provider=provider, model_id="m")
        bound.append(llm.bound_tools)
    assert bound[0] == bound[1] == ["get_metric_definition", "get_dataset_metadata", "run_postgres_query"]


@pytest.mark.parametrize("record,expected", [
    ({"error": "RuntimeError: Bedrock model is not configured (model id is empty)", "stopped_by": "error"}, "not configured"),
    ({"error": "NoCredentialsError: Unable to locate credentials", "stopped_by": "error"}, "credentials"),
    ({"error": "ValidationError: Could not load credentials to authenticate with AWS client", "stopped_by": "error"}, "credentials"),
    ({"error": "ConnectError: connection refused 11434", "stopped_by": "error"}, "Ollama"),
    ({"error": None, "stopped_by": "max_model_calls"}, "maximum number of turns"),
    ({"error": "OperationalError: connection refused", "stopped_by": "error"}, "PostgreSQL"),
])
def test_friendly_errors(record, expected):
    assert expected in chat.friendly_error(record)


def test_details_redact_urls():
    d = chat.safe_details({"error": "boom postgresql://u:secret@host/db", "tool_calls": []})
    assert "secret" not in d["error"]
