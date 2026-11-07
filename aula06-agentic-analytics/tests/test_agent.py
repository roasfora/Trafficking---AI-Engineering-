import json

import pytest
from langchain_core.messages import AIMessage

from config import get_settings
from agent import ALL_TOOLS, NAIVE_TOOLS, build_system_prompt, run_agent


class FakeLLM:
    """Modelo de mentira: devolve respostas guionadas. Sem Bedrock, sem rede."""

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


@pytest.fixture
def settings(tmp_path):
    from dataclasses import replace
    return replace(
        get_settings(), log_path=tmp_path / "requests.jsonl", llm_provider="bedrock",
        bedrock_model_id="fake-model", max_model_calls=4, max_tool_calls=8,
        input_price_per_1m=None, output_price_per_1m=None, max_cost_per_request=None,
    )


def logged(settings):
    return [json.loads(line) for line in settings.log_path.read_text().splitlines()]


def test_tool_flow_and_single_log_record(settings, monkeypatch):
    # run_postgres_query de mentira: este teste nao precisa de PostgreSQL.
    pg_tool = next(t for t in ALL_TOOLS if t.name == "run_postgres_query")
    monkeypatch.setattr(pg_tool, "func", lambda sql: {"columns": ["spend"], "rows": [[426.28]], "row_count": 1})
    sql = "SELECT SUM(cost) FROM marketing.campaign_performance_daily"
    llm = FakeLLM([
        call("get_metric_definition", {"metric_name": "gastámos"}),
        call("run_postgres_query", {"sql": sql}, id="c2"),
        AIMessage(content="426,28 EUR", usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}),
    ])
    record = run_agent("Quanto gastámos ontem na Erobella?", settings, llm=llm)

    assert record["answer"] == "426,28 EUR"
    assert record["stopped_by"] == "end_turn"
    assert record["tool_calls"] == ["get_metric_definition", "run_postgres_query"]
    assert record["sql_queries"] == [sql]
    assert record["model_calls"] == 3
    assert llm.bound_tools == ["get_metric_definition", "get_dataset_metadata", "run_postgres_query"]
    # a definicao governada chegou ao modelo
    assert "SUM(cost)" in llm.seen_messages[-1][3].content
    assert len(logged(settings)) == 1


def test_usage_is_null_when_provider_gives_none(settings):
    record = run_agent("x", settings, llm=FakeLLM([AIMessage(content="ok")]))
    assert record["input_tokens"] is None and record["output_tokens"] is None
    assert record["estimated_model_cost"] is None


def test_estimated_cost_needs_prices(settings):
    from dataclasses import replace
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
    from dataclasses import replace
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


def test_naive_mode_has_no_metric_tool():
    assert "get_metric_definition" in [t.name for t in ALL_TOOLS]
    assert "get_metric_definition" not in [t.name for t in NAIVE_TOOLS]


def test_naive_mode_binds_two_tools_and_prompt_without_metric_rule(settings):
    llm = FakeLLM([AIMessage(content="ok")])
    record = run_agent("x", settings, naive=True, llm=llm)
    assert llm.bound_tools == ["get_dataset_metadata", "run_postgres_query"]
    assert record["naive"] is True
    assert "get_metric_definition" not in build_system_prompt(settings, naive=True)
    assert "get_metric_definition" in build_system_prompt(settings, naive=False)


def test_prompt_knows_yesterday(settings):
    from dataclasses import replace
    from datetime import date
    prompt = build_system_prompt(replace(settings, as_of_date=date(2026, 11, 6)), naive=False)
    assert "2026-11-05" in prompt
