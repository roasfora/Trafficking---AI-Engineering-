"""Internal Business Chatbot (Aula 07): a UI Streamlit sobre o MESMO agente da CLI.

    streamlit run streamlit_app.py

RAG for knowledge, SQL for facts. Muda o modelo/provider; nao muda as tools nem os guardrails.
"""

from __future__ import annotations

import streamlit as st

import chat
from agent import run_agent
from config import get_settings
from providers import PROVIDER_LABELS, aws_credentials_found, bedrock_models, discover_ollama_models, get_llm

EXAMPLES = [
    "O que é CPC e porque não usamos AVG?",
    "O que significa price_eur na Erobella?",
    "Quanto gastámos ontem por provider?",
    "Qual provider teve maior CPC ontem e como definimos CPC?",
    "Qual campanha piorou e existe alguma nota de provider que possa explicar a diferença?",
]

st.set_page_config(page_title="Internal Business Chatbot", page_icon="📊", layout="wide")
settings = get_settings()
if "messages" not in st.session_state:
    st.session_state.messages = []
messages = st.session_state.messages


@st.cache_resource
def cached_llm(provider: str, model_id: str):
    """Um modelo por (provider, model_id): trocar de modelo reconstroi, repetir reutiliza."""
    return get_llm(provider, model_id, get_settings())


# --- sidebar ----------------------------------------------------------------
with st.sidebar:
    provider = st.selectbox("Model Provider", list(PROVIDER_LABELS), format_func=PROVIDER_LABELS.get)
    models: dict[str, str] = {}

    if provider == "bedrock":
        models = bedrock_models(settings)
        if models:
            label = st.selectbox("Model", list(models))
        else:
            label = None
            st.warning("Bedrock model is not configured. Set the BEDROCK_*_MODEL_ID variables in .env.")
        st.caption(f"Region: {settings.aws_region}")
        if models and aws_credentials_found():
            st.success("Status: Configured")
        elif models:
            st.error("AWS credentials were not found.")
    else:
        ollama = discover_ollama_models(settings)
        models = {name: name for name in ollama["models"]}
        if ollama["running"]:
            st.success(f"Ollama: Connected  \nModels found: {len(models)}")
        else:
            st.error("Ollama is not running.\n\nStart it locally and install a model before using this provider.")
        label = st.selectbox("Model", list(models)) if models else None

    model_id = models.get(label) if label else None
    show_details = st.checkbox("Show technical details")
    if st.button("Clear conversation"):
        chat.clear(messages)

# Trocar de modelo nao apaga o historico; so deixa um aviso visual.
choice = (provider, model_id)
if st.session_state.get("choice") not in (None, choice) and model_id and messages:
    chat.add_model_change(messages, f"{PROVIDER_LABELS[provider]} / {label}")
st.session_state["choice"] = choice


# --- helpers de apresentacao --------------------------------------------------
def render_details(record: dict) -> None:
    d = chat.safe_details(record)
    cost = d["estimated_model_cost"]
    with st.expander("Technical details"):
        st.markdown(
            f"- **Provider / model:** {d['provider']} / {d['model']}\n"
            f"- **Model calls:** {d['model_calls']} · **Tool calls:** {len(d['tool_calls'])} "
            f"({', '.join(d['tool_calls']) or '-'})\n"
            f"- **Tokens in / out:** {d['input_tokens'] if d['input_tokens'] is not None else 'unavailable'}"
            f" / {d['output_tokens'] if d['output_tokens'] is not None else 'unavailable'}\n"
            f"- **Latency:** {d['latency_ms']} ms\n"
            f"- **Embedding model:** {d['embedding_model'] or '-'}\n"
            f"- **Retrieved sources:** {', '.join(d['retrieved_sources']) or '-'}\n"
            f"- **Retrieval scores (cosine distance):** {', '.join(map(str, d['retrieval_scores'])) or '-'}\n"
            f"- **Estimated model cost:** {'unavailable' if cost is None else f'${cost}'}\n"
            f"- **Stopped by:** {d['stopped_by']}"
        )
        for sql in d["sql_queries"]:
            st.code(sql, language="sql")
        for chunk in d["retrieved_chunks"]:
            st.caption(f"{chunk['source']} ({chunk['doc_type']}) · distance {chunk['score']}")
            st.text(chunk["text"])
        if d["error"]:
            st.code(d["error"])


# --- pagina principal -----------------------------------------------------------
st.title("Internal Business Chatbot")
st.caption("RAG for knowledge. SQL for facts.")

if not messages:
    st.caption("Try asking:")
    for example in EXAMPLES:
        st.caption(f"• {example}")

for m in messages:
    if m["role"] == "notice":
        st.caption(f"ℹ️ {m['content']}")
        continue
    with st.chat_message(m["role"]):
        (st.error if m.get("failed") else st.write)(m["content"])
        if m.get("record") and chat.sources_markdown(m["record"]):
            st.caption(chat.sources_markdown(m["record"]))
        if show_details and m.get("record"):
            render_details(m["record"])

if question := st.chat_input("Ask a business question...", disabled=model_id is None):
    history = chat.history_for_agent(messages)  # antes de acrescentar esta pergunta
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Analysing..."):
            try:
                llm = cached_llm(provider, model_id)
            except Exception:
                llm = None  # run_agent falha da mesma forma e regista o erro
            record = run_agent(question, settings, llm=llm, history=history, provider=provider, model_id=model_id)
        chat.add_exchange(messages, question, record)
        (st.error if record["error"] else st.write)(messages[-1]["content"])
        if chat.sources_markdown(record):
            st.caption(chat.sources_markdown(record))
        if show_details:
            render_details(record)
