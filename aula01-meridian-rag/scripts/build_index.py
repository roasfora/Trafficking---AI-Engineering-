"""Constroi o indice da base de conhecimento.

    python scripts/build_index.py

Corre isto uma vez antes da primeira utilizacao, e sempre que os documentos
em data/docs mudarem. Demora poucos segundos com 10 documentos.

Este script existe separado da aplicacao de proposito: a indexacao e um
processo offline. Numa empresa a serio isto seria um job agendado que corre
de noite, nao codigo dentro da interface.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.config import settings  # noqa: E402
from meridian.knowledge import build_index, load_documents, split_documents  # noqa: E402
from meridian.models import check_ollama  # noqa: E402


def main() -> int:
    print("=" * 64)
    print(" Meridian AI — construcao do indice")
    print("=" * 64)

    ok, mensagem = check_ollama(settings)
    print(f"  {mensagem}")
    if not ok:
        return 1

    documentos = load_documents(settings)
    if not documentos:
        print(f"  [erro] nenhum ficheiro .md em {settings.docs_dir}")
        return 1

    pedacos = split_documents(documentos, settings)

    print(f"\n  documentos      : {len(documentos)}")
    print(f"  pedacos         : {len(pedacos)}")
    print(f"  chunk_size      : {settings.chunk_size} caracteres")
    print(f"  chunk_overlap   : {settings.chunk_overlap}")
    print(f"  modelo          : {settings.embedding_model}")

    tamanhos = [len(p.page_content) for p in pedacos]
    print(f"  pedaco medio    : {sum(tamanhos) // len(tamanhos)} caracteres")

    print("\n  a gerar embeddings...")
    inicio = time.perf_counter()
    build_index(settings, verbose=True)
    duracao = time.perf_counter() - inicio

    print(f"\n  {len(pedacos)} vetores em {duracao:.1f}s "
          f"({len(pedacos) / duracao:.1f} pedacos/s)")
    print("\n  pronto.  streamlit run app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
