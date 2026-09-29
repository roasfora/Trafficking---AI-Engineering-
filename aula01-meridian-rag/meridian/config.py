"""Configuracao central.

Tudo o que muda entre maquinas vive aqui e em mais lado nenhum.
Nenhum outro ficheiro do projeto chama os.getenv().

Porque isto importa: quando este sistema for para producao, o que muda sao
valores - o host do modelo, o caminho do indice, o numero de documentos a
recuperar. Se estiverem espalhados por dez ficheiros, a migracao e uma cacada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # opcional: permite um ficheiro .env sem o tornar obrigatorio
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    # --- modelos --------------------------------------------------------
    # O modelo de chat: gera as respostas.
    chat_model: str = "llama3.1:8b"
    # O modelo de embeddings: transforma texto em vetores. E OUTRO modelo,
    # muito mais pequeno (274 MB contra 4.9 GB), treinado para uma so tarefa.
    embedding_model: str = "nomic-embed-text"
    ollama_host: str = "http://localhost:11434"

    # 0.0 = deterministico. Para um assistente que responde sobre documentos
    # internos queremos baixo: nao ha nada de criativo em citar uma politica.
    temperature: float = 0.2

    # --- indexacao ------------------------------------------------------
    # Tamanho de cada pedaco de documento, em caracteres.
    # Pequeno demais: perde-se o contexto. Grande demais: o pedaco recuperado
    # traz muito ruido e a resposta piora. 900/150 e um bom ponto de partida
    # para documentacao interna em markdown.
    chunk_size: int = 900
    chunk_overlap: int = 150

    # Quantos pedacos entregamos ao modelo por pergunta.
    # Mais contexto nao e sempre melhor: enche a janela, aumenta a latencia,
    # e a atencao degrada-se a meio de contextos longos.
    top_k: int = 4

    # --- conversa -------------------------------------------------------
    # Quantas mensagens do historico reenviamos. O modelo nao tem memoria:
    # a conversa existe porque nos a reenviamos a cada pergunta.
    max_history_messages: int = 10

    # --- caminhos -------------------------------------------------------
    docs_dir: Path = ROOT / "data" / "docs"
    index_path: Path = ROOT / "data" / "index" / "store.json"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            chat_model=os.getenv("MERIDIAN_CHAT_MODEL", "llama3.1:8b"),
            embedding_model=os.getenv("MERIDIAN_EMBEDDING_MODEL", "nomic-embed-text"),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            temperature=float(os.getenv("MERIDIAN_TEMPERATURE", "0.2")),
            chunk_size=int(os.getenv("MERIDIAN_CHUNK_SIZE", "900")),
            chunk_overlap=int(os.getenv("MERIDIAN_CHUNK_OVERLAP", "150")),
            top_k=int(os.getenv("MERIDIAN_TOP_K", "4")),
            max_history_messages=int(os.getenv("MERIDIAN_MAX_HISTORY", "10")),
        )


settings = Settings.from_env()
