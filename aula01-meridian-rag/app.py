"""Meridian AI Assistant — interface em Streamlit.

    streamlit run app.py

Este ficheiro nao sabe nada sobre RAG, sobre Ollama, nem sobre grafos.
Sabe desenhar uma conversa e chamar duas funcoes: `stream_answer` e
`get_last_state`. Essa separacao e de proposito — a interface e a camada que
mais muda, e a que menos deve saber.

A barra lateral tem um "modo instrutor" que mostra o caminho que o grafo tomou,
os pedacos recuperados e as pontuacoes de semelhanca. E o que transforma uma
demonstracao numa aula.
"""

from __future__ import annotations

import uuid

import streamlit as st

from meridian import __version__
from meridian.config import settings
from meridian.graph import build_graph, get_last_state, stream_answer
from meridian.knowledge import build_index, index_exists, load_index
from meridian.models import check_ollama

LIME = "#C8F03C"

PERGUNTAS_EXEMPLO = [
    "Qual foi o CPA da campanha VG-Aquisicao-PT no Q3?",
    "Qual e o frequency cap para campanhas de iGaming?",
    "Quem aprova um aumento de budget de 40 000 EUR?",
    "O que correu mal no incidente de tracking de setembro?",
    "Quanto tempo demora o onboarding de um cliente novo?",
    "Qual foi a receita da Meridian em 2019?",
]


# ---------------------------------------------------------------------------
# Recursos caros — carregados uma vez, nao a cada interacao
# ---------------------------------------------------------------------------
# O Streamlit re-executa este ficheiro de cima a baixo a cada clique. Sem
# `cache_resource`, o indice seria lido do disco e o grafo reconstruido a cada
# tecla. Estas duas linhas sao a diferenca entre uma app usavel e uma app
# insuportavel.


@st.cache_resource(show_spinner="A carregar a base de conhecimento...")
def get_store():
    return load_index(settings)


@st.cache_resource(show_spinner="A montar o grafo...")
def get_graph():
    return build_graph(get_store(), settings)


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Meridian AI Assistant",
    page_icon="◆",
    layout="centered",
)

# O tema (fundo escuro, accent lima) esta em .streamlit/config.toml.
# Aqui so definimos as etiquetas de rota, que nao tem equivalente nativo.
st.markdown(
    f"""
    <style>
      .rota {{
        display:inline-block; padding:3px 12px; border-radius:12px;
        font-size:11px; font-weight:700; letter-spacing:1.2px;
      }}
      .rota-k {{ background:{LIME}; color:#0D0D0D; }}
      .rota-c {{ background:#2A2A2A; color:#9A9A9A; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Meridian AI Assistant")
st.caption(
    f"v{__version__} · RAG sobre a documentação interna · "
    "corre localmente, nada sai desta máquina"
)


# ---------------------------------------------------------------------------
# Estado da sessao
# ---------------------------------------------------------------------------
# `thread_id` e o identificador da conversa para o checkpointer do LangGraph.
# Uma thread = um historico. Mudar de thread = comecar uma conversa nova
# sem perder a anterior.

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "historico" not in st.session_state:
    st.session_state.historico = []  # [(papel, texto, meta)]
if "pergunta_pendente" not in st.session_state:
    st.session_state.pergunta_pendente = None


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Estado do sistema")

    ok, mensagem = check_ollama(settings)
    if ok:
        st.success(mensagem)
    else:
        st.error(mensagem)

    if index_exists(settings):
        st.info(f"Índice: `{settings.index_path.name}`")
    else:
        st.warning("Índice ainda não construído.")

    st.divider()
    st.subheader("Configuração")
    st.write(f"**Chat:** `{settings.chat_model}`")
    st.write(f"**Embeddings:** `{settings.embedding_model}`")
    st.write(f"**top_k:** {settings.top_k} · **temp:** {settings.temperature}")
    st.write(f"**Histórico:** {settings.max_history_messages} mensagens")

    st.divider()
    modo_instrutor = st.toggle("Modo instrutor", value=True, help="Mostra o caminho do grafo, os pedaços recuperados e as pontuações.")

    st.divider()
    if st.button("Reconstruir índice", use_container_width=True):
        with st.spinner("A gerar embeddings..."):
            build_index(settings, verbose=True)
        st.cache_resource.clear()
        st.success("Índice reconstruído.")
        st.rerun()

    if st.button("Nova conversa", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.historico = []
        st.rerun()

    if modo_instrutor and ok and index_exists(settings):
        with st.expander("O grafo"):
            st.code(get_graph().get_graph().draw_mermaid(), language="text")
        st.caption(f"thread_id: `{st.session_state.thread_id[:8]}`")


# ---------------------------------------------------------------------------
# Portoes de entrada — falhar cedo, com uma instrucao acionavel
# ---------------------------------------------------------------------------

if not ok:
    st.error(mensagem)
    st.info(
        "Assim que o Ollama estiver a responder, recarrega a página. "
        "O resto da aplicação não precisa de internet."
    )
    st.stop()

if not index_exists(settings):
    st.warning(
        "A base de conhecimento ainda não foi indexada. "
        f"São {len(list(settings.docs_dir.glob('*.md')))} documentos em `data/docs/`."
    )
    if st.button("Construir índice agora", type="primary"):
        with st.spinner("A gerar embeddings — isto corre uma vez..."):
            build_index(settings, verbose=True)
        st.cache_resource.clear()
        st.rerun()
    st.caption("Em alternativa, no terminal: `python scripts/build_index.py`")
    st.stop()


# ---------------------------------------------------------------------------
# Perguntas de exemplo
# ---------------------------------------------------------------------------

if not st.session_state.historico:
    st.write("**Experimenta:**")
    colunas = st.columns(2)
    for i, pergunta in enumerate(PERGUNTAS_EXEMPLO):
        if colunas[i % 2].button(pergunta, use_container_width=True, key=f"ex{i}"):
            st.session_state.pergunta_pendente = pergunta
            st.rerun()
    st.caption(
        "A última é de propósito: a resposta não existe na documentação. "
        "Repara no que o assistente faz."
    )


# ---------------------------------------------------------------------------
# Conversa
# ---------------------------------------------------------------------------


def mostrar_meta(meta: dict) -> None:
    """Mostra a rota tomada e as fontes citadas — o painel de raio-x."""
    if not meta:
        return

    rota = meta.get("route", "chat")
    etiqueta = (
        '<span class="rota rota-k">CONSULTOU A BASE DE CONHECIMENTO</span>'
        if rota == "knowledge"
        else '<span class="rota rota-c">RESPONDEU DIRETO</span>'
    )
    st.markdown(etiqueta, unsafe_allow_html=True)

    contexto = meta.get("context") or []
    if not contexto:
        return

    with st.expander(f"Pedaços recuperados ({len(contexto)})"):
        for i, (doc, score) in enumerate(contexto, start=1):
            st.markdown(
                f"**[{i}] {doc.metadata.get('title', '')}** · "
                f"`{doc.metadata.get('source', '?')}` · "
                f"semelhança **{score:.3f}**"
            )
            st.text(doc.page_content[:600] + ("..." if len(doc.page_content) > 600 else ""))
            st.divider()


for papel, texto, meta in st.session_state.historico:
    with st.chat_message(papel):
        st.markdown(texto)
        if papel == "assistant" and modo_instrutor:
            mostrar_meta(meta)


pergunta = st.chat_input("Pergunta sobre a documentação interna...")
if st.session_state.pergunta_pendente:
    pergunta = st.session_state.pergunta_pendente
    st.session_state.pergunta_pendente = None

if pergunta:
    st.session_state.historico.append(("user", pergunta, {}))
    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        grafo = get_graph()
        # `st.write_stream` consome o gerador e desenha os tokens a medida
        # que chegam. O streaming nao e um truque de interface: e literalmente
        # assim que o modelo gera, um token de cada vez.
        resposta = st.write_stream(
            stream_answer(grafo, pergunta, st.session_state.thread_id)
        )

        # Depois de responder, lemos o estado guardado pelo checkpointer para
        # saber que caminho foi tomado e o que foi recuperado.
        estado = get_last_state(grafo, st.session_state.thread_id)
        meta = {"route": estado.get("route"), "context": estado.get("context")}

        if modo_instrutor:
            mostrar_meta(meta)

    st.session_state.historico.append(("assistant", resposta, meta))
