"""Indexe le PDF du DEU : `python scripts/ingest.py` (depuis backend/, venv activé).

À lancer une fois (ou quand le PDF change). Nécessite GEMINI_API_KEY dans le .env.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # pour `import app`

from langchain_google_genai import GoogleGenerativeAIEmbeddings  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.rag import build_index, load_chunks, load_pdf_pages, split_documents  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    settings = get_settings()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY manquante dans le .env")
    # Chunks propres déjà extraits de préférence ; sinon extraction + découpage du PDF.
    if settings.rag_chunks_path.exists():
        chunks = load_chunks(settings.rag_chunks_path)
    elif settings.rag_pdf_path.exists():
        chunks = split_documents(load_pdf_pages(settings.rag_pdf_path))
    else:
        sys.exit(f"Ni chunks ({settings.rag_chunks_path}) ni PDF ({settings.rag_pdf_path})")
    keys = [settings.gemini_api_key]
    keys += [k.strip() for k in settings.gemini_api_keys_extra.split(",") if k.strip()]
    embeddings = [
        GoogleGenerativeAIEmbeddings(model=settings.gemini_embedding_model, google_api_key=key)
        for key in keys
    ]
    print(f"{len(keys)} clé(s) API, {len(chunks)} chunks")
    count = build_index(chunks, embeddings, settings.rag_index_path)
    print(f"{count} chunks indexés -> {settings.rag_index_path}")


if __name__ == "__main__":
    main()
