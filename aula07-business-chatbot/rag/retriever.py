"""Retriever: o vector store (PGVector) e uma funcao de pesquisa simples.

Tudo o que o RAG faz em runtime esta aqui: embeber a pergunta e pedir os k chunks
mais proximos (distancia coseno: MENOR = mais parecido).
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGVector
from sqlalchemy import create_engine

from config import Settings, get_settings


def get_embeddings(settings: Settings | None = None) -> OllamaEmbeddings:
    settings = settings or get_settings()
    return OllamaEmbeddings(model=settings.embedding_model, base_url=settings.ollama_base_url)


def get_vector_store(
    settings: Settings | None = None,
    writer: bool = False,
    embeddings=None,
    pre_delete_collection: bool = False,
) -> PGVector:
    """PGVector no schema `knowledge`. writer=True usa o dono (indexacao);
    o runtime usa o role knowledge_reader (so SELECT)."""
    settings = settings or get_settings()
    url = settings.index_database_url if writer else settings.knowledge_database_url
    # search_path: as tabelas do langchain-postgres ficam no schema knowledge (e o tipo vector vem de public)
    engine = create_engine(url, connect_args={"options": "-c search_path=knowledge,public"})
    return PGVector(
        embeddings=embeddings or get_embeddings(settings),
        collection_name=settings.knowledge_collection,
        connection=engine,
        use_jsonb=True,
        create_extension=False,  # a extensao e criada em sql/01_extensions.sql
        pre_delete_collection=pre_delete_collection,
    )


def get_retriever(k: int = 4, settings: Settings | None = None):
    """Retriever LangChain standard (sem scores). A tool usa `search` abaixo, que devolve scores."""
    return get_vector_store(settings).as_retriever(search_kwargs={"k": k})


def search(
    query: str, k: int | None = None, settings: Settings | None = None, store: PGVector | None = None
) -> list[tuple[Document, float]]:
    """(chunk, distancia) dos k mais proximos, descartando os acima de KNOWLEDGE_MAX_DISTANCE."""
    settings = settings or get_settings()
    store = store or get_vector_store(settings)
    results = store.similarity_search_with_score(query, k=k or settings.knowledge_k)
    if settings.knowledge_max_distance is not None:
        results = [(doc, score) for doc, score in results if score <= settings.knowledge_max_distance]
    return results
