"""A FRONTEIRA DO PROVIDER.

Este e o unico ficheiro do projeto que sabe que existe um Ollama.

    app.py  /  graph.py  /  knowledge.py      <- nunca importam ollama
                    |
              models.py                       <- ESTA FRONTEIRA
                    |
            ChatOllama + OllamaEmbeddings
                    |
               Ollama local

Porque isto e a decisao de arquitetura mais importante do projeto:

    Para migrar para a AWS, este ficheiro passa a ser:

        from langchain_aws import ChatBedrock, BedrockEmbeddings

        def get_chat_model(...):
            return ChatBedrock(model_id="anthropic.claude-...", ...)

        def get_embeddings():
            return BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0")

    E mais nada muda. Nem o grafo, nem o retriever, nem a interface.
    Isto e possivel porque o LangChain define interfaces comuns
    (BaseChatModel e Embeddings) que todos os providers implementam.
"""

from __future__ import annotations

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings

from meridian.config import Settings, settings


def get_chat_model(
    config: Settings | None = None,
    *,
    temperature: float | None = None,
) -> BaseChatModel:
    """Devolve o modelo de chat.

    Repara no tipo de retorno: `BaseChatModel`, nao `ChatOllama`.
    O resto do projeto so pode contar com o que existe na interface comum -
    e e por isso que trocar de provider nao parte nada.
    """
    config = config or settings
    return ChatOllama(
        model=config.chat_model,
        base_url=config.ollama_host,
        temperature=config.temperature if temperature is None else temperature,
    )


def get_embeddings(config: Settings | None = None) -> Embeddings:
    """Devolve o modelo de embeddings.

    REGRA CRITICA: tem de ser o mesmo modelo usado para indexar e para
    consultar. Espacos vetoriais diferentes nao sao comparaveis. Trocar de
    modelo de embeddings obriga a reindexar tudo - e o erro nao rebenta,
    so devolve resultados maus.
    """
    config = config or settings
    return OllamaEmbeddings(
        model=config.embedding_model,
        base_url=config.ollama_host,
    )


def check_ollama(config: Settings | None = None) -> tuple[bool, str]:
    """Diagnostico: o servidor responde e os dois modelos estao instalados?

    Falhar cedo, com uma mensagem que diz o que fazer, vale mais do que um
    traceback a meio de uma demonstracao.
    """
    config = config or settings
    try:
        response = httpx.get(f"{config.ollama_host}/api/tags", timeout=5.0)
        response.raise_for_status()
        installed = [m["name"] for m in response.json().get("models", [])]
    except Exception:  # noqa: BLE001
        return False, (
            f"Nao consigo falar com o Ollama em {config.ollama_host}. "
            "Arranca o servidor com `ollama serve` ou abre a aplicacao Ollama."
        )

    def has(model: str) -> bool:
        base = model.split(":")[0]
        return any(name.split(":")[0] == base for name in installed)

    missing = [m for m in (config.chat_model, config.embedding_model) if not has(m)]
    if missing:
        comandos = "  ".join(f"`ollama pull {m}`" for m in missing)
        return False, f"Faltam modelos: {', '.join(missing)}. Corre: {comandos}"

    return True, f"Ollama pronto. Modelos instalados: {', '.join(installed)}"
