import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from agent import ALL_TOOLS, run_agent
from config import get_settings


class FakeLLM:
    """Modelo de mentira: devolve respostas guionadas. Sem Bedrock, sem Ollama, sem rede."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.bound_tools = None
        self.seen_messages = []

    def bind_tools(self, tools):
        self.bound_tools = [t.name for t in tools]
        return self

    def invoke(self, messages):
        self.seen_messages.append(list(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def call(name, args, id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


def tool(name):
    return next(t for t in ALL_TOOLS if t.name == name)


@pytest.fixture
def settings(tmp_path):
    return replace(
        get_settings(), log_path=tmp_path / "requests.jsonl", llm_provider="bedrock",
        bedrock_model_id="fake-model", max_model_calls=4, max_tool_calls=8,
        input_price_per_1m=None, output_price_per_1m=None, max_cost_per_request=None,
    )


def logged(settings):
    return [json.loads(line) for line in settings.log_path.read_text().splitlines()]


def test_registry_has_exactly_the_four_expected_tools():
    assert [t.name for t in ALL_TOOLS] == [
        "search_internal_knowledge", "get_metric_definition", "get_dataset_metadata", "run_postgres_query",
    ]


def test_every_tool_has_a_description_for_the_model():
    assert all(len(t.description) > 40 for t in ALL_TOOLS)
    assert "Do NOT use it to answer current numbers" in tool("search_internal_knowledge").description


def test_sql_flow_and_single_log_record(settings, monkeypatch):
    monkeypatch.setattr(tool("run_postgres_query"), "func", lambda sql: {"columns": ["spend"], "rows": [[424.59]], "row_count": 1})
    sql = "SELECT SUM(cost) FROM analytics.campaign_performance_daily"
    llm = FakeLLM([
        call("get_metric_definition", {"metric_name": "gastámos"}),
        call("run_postgres_query", {"sql": sql}, id="c2"),
        AIMessage(content="424,59 EUR", usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}),
    ])
    record = run_agent("Quanto gastámos ontem na Erobella?", settings, llm=llm)

    assert record["answer"] == "424,59 EUR"
    assert record["stopped_by"] == "end_turn"
    assert record["tool_calls"] == ["get_metric_definition", "run_postgres_query"]
    assert record["sql_queries"] == [sql]
    assert record["retrieved_sources"] == [] and record["embedding_model"] is None
    assert llm.bound_tools == [t.name for t in ALL_TOOLS]
    assert "SUM(cost)" in llm.seen_messages[-1][3].content  # a definicao governada chegou ao modelo
    assert len(logged(settings)) == 1


def test_receipt_captures_retrieval_metadata(settings, monkeypatch):
    hits = {"results": [
        {"text": "CPC = spend / clicks", "source": "business_glossary.md", "doc_type": "glossary", "score": 0.2788},
        {"text": "CPC - Cost per Click ...", "source": "semantic.yaml#cpc", "doc_type": "metric_definition", "score": 0.3172},
        {"text": "outro chunk", "source": "business_glossary.md", "doc_type": "glossary", "score": 0.3146},
    ]}
    monkeypatch.setattr(tool("search_internal_knowledge"), "func", lambda query: hits)
    llm = FakeLLM([call("search_internal_knowledge", {"query": "O que e CPC?"}), AIMessage(content="CPC e ...")])
    record = run_agent("O que e CPC?", settings, llm=llm)

    assert record["retrieved_sources"] == ["business_glossary.md", "semantic.yaml#cpc"]  # sem duplicados
    assert record["retrieval_scores"] == [0.2788, 0.3172, 0.3146]
    assert len(record["retrieved_chunks"]) == 3 and record["retrieved_chunks"][1]["doc_type"] == "metric_definition"
    assert record["embedding_model"] == settings.embedding_model
    assert record["sql_queries"] == []
    [line] = logged(settings)  # o mesmo vai para o log
    assert line["retrieved_sources"] == record["retrieved_sources"]


def test_receipt_text_shows_retrieval_fields(settings):
    from observability import format_receipt

    record = run_agent("x", settings, llm=FakeLLM([AIMessage(content="ok")]))
    text = format_receipt(record)
    for label in ("Retrieved sources", "Retrieval scores", "Retrieved chunks", "Embedding model"):
        assert label in text


def test_usage_is_null_when_provider_gives_none(settings):
    record = run_agent("x", settings, llm=FakeLLM([AIMessage(content="ok")]))
    assert record["input_tokens"] is None and record["output_tokens"] is None
    assert record["estimated_model_cost"] is None


def test_estimated_cost_needs_prices(settings):
    priced = replace(settings, input_price_per_1m=3.0, output_price_per_1m=15.0)
    msg = AIMessage(content="ok", usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100})
    assert run_agent("x", priced, llm=FakeLLM([msg]))["estimated_model_cost"] == 0.0045
    assert run_agent("x", settings, llm=FakeLLM([msg]))["estimated_model_cost"] is None


def test_max_model_calls_stops_loop(settings):
    llm = FakeLLM([call("get_metric_definition", {"metric_name": "spend"}, id=f"c{i}") for i in range(10)])
    record = run_agent("x", settings, llm=llm)
    assert record["stopped_by"] == "max_model_calls"
    assert record["model_calls"] == settings.max_model_calls
    assert "limites" in record["answer"]


def test_max_cost_stops_loop(settings):
    s = replace(settings, input_price_per_1m=1000.0, output_price_per_1m=1000.0, max_cost_per_request=0.01)
    msg = call("get_metric_definition", {"metric_name": "spend"})
    msg.usage_metadata = {"input_tokens": 1000, "output_tokens": 1000, "total_tokens": 2000}
    record = run_agent("x", s, llm=FakeLLM([msg, msg]))
    assert record["stopped_by"] == "max_cost" and record["model_calls"] == 1


def test_model_failure_is_logged_and_returned(settings):
    record = run_agent("x", settings, llm=FakeLLM([RuntimeError("Bedrock down")]))
    assert record["stopped_by"] == "error"
    assert "Bedrock down" in record["error"]
    assert record["latency_ms"] is not None
    [line] = logged(settings)
    assert line["stopped_by"] == "error"


def test_unknown_tool_goes_back_to_model_not_executed(settings):
    llm = FakeLLM([call("run_shell", {"cmd": "ls"}), AIMessage(content="ok")])
    record = run_agent("x", settings, llm=llm)
    assert record["stopped_by"] == "end_turn"
    assert "Unknown tool" in llm.seen_messages[-1][-1].content


def test_system_prompt_teaches_rag_for_knowledge_sql_for_facts(settings):
    from agent import build_system_prompt

    prompt = build_system_prompt(settings)
    assert "RAG for knowledge. SQL for facts." in prompt
    for name in (t.name for t in ALL_TOOLS):
        assert name in prompt
    assert "NUNCA respondas a perguntas numericas atuais com base em documentos" in prompt
    assert "NUNCA inventes politica interna" in prompt
