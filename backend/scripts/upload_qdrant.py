"""Envoie l'index local dans Qdrant Cloud : `python scripts/upload_qdrant.py` (depuis backend/).

Réutilise les vecteurs de `index.json.gz` : aucun appel à Gemini. Relançable sans doublons.
Nécessite QDRANT_URL et QDRANT_API_KEY dans le .env.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # pour `import app`

from qdrant_client import QdrantClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.rag import upload_index_to_qdrant  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    settings = get_settings()
    if not settings.qdrant_url:
        sys.exit("QDRANT_URL manquante dans le .env")
    if not settings.rag_index_path.exists():
        sys.exit(f"Index introuvable : {settings.rag_index_path}")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    count = upload_index_to_qdrant(settings.rag_index_path, client, settings.qdrant_collection)
    print(f"{count} points -> {settings.qdrant_collection}")


if __name__ == "__main__":
    main()
