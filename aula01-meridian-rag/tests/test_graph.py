"""Testes do grafo, sem Ollama.

Ponto pedagogico: a maior parte de um sistema de IA e testavel como codigo
normal. So a chamada ao modelo e que nao e. Injetamos modelos falsos e
verificamos o que interessa — o routing, o estado, a memoria entre turnos e a
montagem do contexto.

    pytest -q
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.vectorstores import InMemoryVectorStore

from meridian.config import Settings
from meridian.graph import ask, build_graph, get_last_state, route_question
from meridian.knowledge import format_context, split_documents


# --- utilitarios -----------------------------------------------------------


class RouterFalso(FakeMessagesListChatModel):
    """Devolve sempre a mesma rota, para testarmos as duas ramificacoes."""


def montar(rota: str, resposta: str = "resposta de teste"):
    store = InMemoryVectorStore(embedding=FakeEmbeddings(size=16))
    store.add_documents(
        [
            Document(
                page_content="O CPA da VG-Aquisicao-PT foi de 33,10 EUR.",
                metadata={"source": "02_relatorio.md", "title": "Relatorio Q3"},
            ),
            Document(
                page_content="O frequency cap de iGaming e de 3 por semana.",
                metadata={"source": "03_compliance.md", "title": "Compliance"},
            ),
        ]
    )
    config = Settings(top_k=2, max_history_messages=6)
    graph = build_graph(
        store,
        config,
        llm=FakeMessagesListChatModel(responses=[AIMessage(content=resposta)] * 20),
        router_llm=FakeMessagesListChatModel(responses=[AIMessage(content=rota)] * 20),
    )
    return graph


# --- routing ---------------------------------------------------------------


def test_route_question_le_o_estado():
    assert route_question({"route": "knowledge"}) == "retrieve"
    assert route_question({"route": "chat"}) == "generate"
    assert route_question({}) == "generate"  # sem rota, nao recupera nada


def test_rota_knowledge_passa_pelo_retrieve():
    graph = montar("knowledge")
    estado = ask(graph, "Qual foi o CPA da VG-Aquisicao-PT?", "t1")
    assert estado["route"] == "knowledge"
    assert len(estado["context"]) == 2
    assert estado["sources"]  # o retrieve preencheu as fontes


def test_rota_chat_nao_recupera_nada():
    graph = montar("chat")
    estado = ask(graph, "bom dia", "t2")
    assert estado["route"] == "chat"
    assert not estado.get("context")
    assert not estado.get("sources")


def test_classificador_a_falhar_cai_na_heuristica():
    """Se o modelo devolver lixo, a rede de seguranca por palavras-chave decide."""
    graph = montar("!!! resposta invalida !!!")
    assert ask(graph, "Qual foi o CPA da campanha?", "t3")["route"] == "knowledge"
    assert ask(graph, "obrigado, bom fim de semana", "t4")["route"] == "chat"


# --- memoria ---------------------------------------------------------------


def test_o_historico_cresce_dentro_da_mesma_thread():
    graph = montar("chat")
    ask(graph, "primeira", "mesma-thread")
    estado = ask(graph, "segunda", "mesma-thread")
    # 2 perguntas + 2 respostas
    assert len(estado["messages"]) == 4


def test_threads_diferentes_tem_historicos_independentes():
    graph = montar("chat")
    ask(graph, "ola", "thread-a")
    estado_b = ask(graph, "ola", "thread-b")
    assert len(estado_b["messages"]) == 2


def test_o_checkpointer_guarda_o_estado_entre_chamadas():
    graph = montar("knowledge")
    ask(graph, "Qual e o frequency cap?", "t5")
    guardado = get_last_state(graph, "t5")
    assert guardado["route"] == "knowledge"
    assert guardado["sources"]


# --- knowledge -------------------------------------------------------------


def test_o_contexto_e_numerado_e_cita_a_fonte():
    docs = [
        (Document(page_content="texto A", metadata={"source": "a.md", "title": "A"}), 0.9),
        (Document(page_content="texto B", metadata={"source": "b.md", "title": "B"}), 0.4),
    ]
    contexto = format_context(docs)
    assert "[1]" in contexto and "[2]" in contexto
    assert "a.md" in contexto and "b.md" in contexto


def test_o_splitter_respeita_o_tamanho_configurado():
    documento = Document(page_content="frase. " * 500, metadata={"source": "x.md"})
    pedacos = split_documents([documento], Settings(chunk_size=300, chunk_overlap=50))
    assert len(pedacos) > 1
    assert all(len(p.page_content) <= 400 for p in pedacos)
    assert all(p.metadata["source"] == "x.md" for p in pedacos)


def test_os_documentos_reais_carregam_e_partem():
    from meridian.config import settings
    from meridian.knowledge import load_documents

    documentos = load_documents(settings)
    assert len(documentos) >= 10
    assert all(d.metadata["title"] for d in documentos)
    pedacos = split_documents(documentos, settings)
    assert len(pedacos) > len(documentos)


# --- estrutura do grafo ----------------------------------------------------


def test_o_grafo_tem_os_tres_nos_e_a_aresta_condicional():
    graph = montar("chat")
    desenho = graph.get_graph()
    nomes = set(desenho.nodes)
    assert {"classify", "retrieve", "generate"} <= nomes
    mermaid = desenho.draw_mermaid()
    # a aresta condicional aparece tracejada
    assert "classify -.->" in mermaid
