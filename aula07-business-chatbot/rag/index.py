"""Indexacao explicita:  python -m rag.index

    knowledge/*.md  +  Documents de metricas (semantic.yaml)
        -> RecursiveCharacterTextSplitter
        -> OllamaEmbeddings (nomic-embed-text)
        -> PGVector (schema knowledge, colecao internal_knowledge)

So conhecimento (texto) vai para o vector store. Linhas de dados operacionais NAO:
numeros vivem no PostgreSQL e consultam-se com SQL.
"""

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings, get_settings
from rag.metric_documents import metric_documents
from rag.retriever import get_embeddings, get_vector_store

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# ficheiro -> tipo de documento (fica na metadata e no recibo)
DOC_TYPES = {
    "business_glossary.md": "glossary",
    "conversion_definitions.md": "definition",
    "attribution_policy.md": "policy",
    "provider_notes.md": "provider_note",
    "campaign_definitions.md": "definition",
    "malicious_note.md": "security_test",  # demo de prompt injection: ver README
}


def load_markdown_documents(directory: Path = KNOWLEDGE_DIR) -> list[Document]:
    docs = []
    for path in sorted(directory.glob("*.md")):
        docs.append(
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata={"source": path.name, "doc_type": DOC_TYPES.get(path.name, "knowledge")},
            )
        )
    return docs


def split_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(docs)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk"] = i
    return chunks


def build_index(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    docs = load_markdown_documents() + metric_documents()
    chunks = split_documents(docs)
    # pre_delete_collection=True: reindexar substitui a colecao (idempotente)
    store = get_vector_store(settings, writer=True, pre_delete_collection=True)
    store.add_documents(chunks)
    print(f"{len(docs)} documents -> {len(chunks)} chunks  (embeddings: {settings.embedding_model})")
    return len(chunks)


if __name__ == "__main__":
    try:
        build_index()
    except Exception as exc:  # Ollama em baixo, modelo em falta, PostgreSQL em baixo...
        print(f"Index failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Check: docker compose up -d | ollama pull nomic-embed-text", file=sys.stderr)
        sys.exit(1)
