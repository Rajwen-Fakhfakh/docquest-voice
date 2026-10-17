"""RAG (Retrieval-Augmented Generation) : retrouver les passages du DEU utiles à une question.

Principe en 2 temps :
  1. INDEXATION (une seule fois, `scripts/ingest.py`) :
       PDF -> texte par page -> découpage en chunks -> embeddings -> fichier JSON
  2. REQUÊTE (à chaque question) :
       question -> embedding -> chunks les plus proches -> injectés dans le prompt du LLM

Tout est fait avec des briques LangChain simples, sans base de données externe.
"""

import gzip
import json
import logging
import time
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ~1000 caractères ≈ un paragraphe : assez pour du contexte, assez petit pour être précis.
CHUNK_SIZE = 1000
# Le chevauchement évite de couper une idée en deux entre deux chunks.
CHUNK_OVERLAP = 150
# Palier gratuit Gemini : 100 textes/minute. Chaque chunk compte comme une requête, donc
# on envoie 40 chunks puis on attend 30 s (~80/min), et on retente si l'API répond 429.
BATCH_SIZE = 40
BATCH_PAUSE_SECONDS = 30.0
RETRY_WAIT_SECONDS = 60.0
MAX_RETRIES = 5


def load_pdf_pages(pdf_path: Path) -> list[Document]:
    """Un `Document` par page, avec le numéro de page en métadonnée (pour citer les sources)."""
    reader = PdfReader(str(pdf_path))
    pages: list[Document] = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:  # on saute les pages sans texte (images seules)
            pages.append(Document(page_content=text, metadata={"page": number}))
    return pages


def split_documents(pages: list[Document]) -> list[Document]:
    """Découpe chaque page en chunks ; les métadonnées (page) sont conservées."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return splitter.split_documents(pages)


class DailyQuotaExceeded(Exception):
    """Le quota journalier de la clé courante est épuisé (inutile d'attendre)."""


def _add_with_retry(store: InMemoryVectorStore, batch: list[Document]) -> None:
    """Ajoute un lot ; si le quota par minute est dépassé (429), attend puis réessaie."""
    for attempt in range(MAX_RETRIES):
        try:
            store.add_documents(batch)
            return
        except Exception as exc:
            message = str(exc)
            if "RESOURCE_EXHAUSTED" not in message:
                raise
            if "PerDay" in message:
                raise DailyQuotaExceeded(message) from exc
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning("Quota dépassé, nouvel essai dans %.0f s", RETRY_WAIT_SECONDS)
            time.sleep(RETRY_WAIT_SECONDS)


def load_chunks(chunks_path: Path) -> list[Document]:
    """Charge des chunks déjà extraits et nettoyés (JSONL : `id`, `page`, `text`)."""
    chunks: list[Document] = []
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            chunks.append(Document(page_content=row["text"], metadata={"page": row["page"]}))
    return chunks


# 6 décimales : l'écart sur la similarité cosinus est ~1e-6, et le fichier est 25 % plus léger.
VECTOR_DECIMALS = 6


def save_index(store: InMemoryVectorStore, index_path: Path) -> None:
    """Écrit l'index en JSON compact, compressé en gzip si `index_path` finit par `.gz`.

    Compact + arrondi + gzip : ~28 Mo au lieu de 190 Mo, donc versionnable dans git.
    """
    entries = {
        entry_id: {**entry, "vector": [round(x, VECTOR_DECIMALS) for x in entry["vector"]]}
        for entry_id, entry in store.store.items()
    }
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if index_path.suffix == ".gz":
        payload = gzip.compress(payload, compresslevel=6)
    index_path.write_bytes(payload)


def load_index(index_path: Path, embeddings: Embeddings) -> InMemoryVectorStore:
    """Relit un index écrit par `save_index` (`.json` ou `.json.gz`)."""
    raw = index_path.read_bytes()
    if index_path.suffix == ".gz":
        raw = gzip.decompress(raw)
    store = InMemoryVectorStore(embeddings)
    store.store = json.loads(raw)
    return store


def build_index(chunks: list[Document], embeddings: list[Embeddings], index_path: Path) -> int:
    """Calcule les embeddings des chunks et sauvegarde dans `index_path`. Retourne leur nombre.

    `embeddings` : une instance par clé API. Quand le quota journalier d'une clé est épuisé,
    on passe à la suivante (même modèle, donc vecteurs compatibles).

    La progression est écrite après chaque lot dans `<index>.partial` : si le script s'arrête
    (quota, coupure), relancer reprend là où il en était, sans repayer les embeddings déjà faits.
    """
    partial = index_path.with_name(index_path.name + ".partial")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    key_index = 0
    store = InMemoryVectorStore(embeddings[key_index])
    if partial.exists():
        with partial.open(encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                store.store[entry["id"]] = entry
        logger.info("Reprise : %d chunks déjà indexés", len(store.store))
    done = len(store.store)  # les chunks sont traités dans l'ordre, donc `done` = nb déjà faits

    for start in range(done, len(chunks), BATCH_SIZE):
        known = set(store.store)
        while True:
            try:
                _add_with_retry(store, chunks[start : start + BATCH_SIZE])
                break
            except DailyQuotaExceeded:
                key_index += 1
                if key_index >= len(embeddings):
                    raise
                logger.warning("Quota journalier épuisé, bascule sur la clé %d", key_index + 1)
                store.embedding = embeddings[key_index]
        with partial.open("a", encoding="utf-8") as f:
            for entry_id, entry in store.store.items():
                if entry_id not in known:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("Indexé %d/%d chunks", min(start + BATCH_SIZE, len(chunks)), len(chunks))
        time.sleep(BATCH_PAUSE_SECONDS)
    save_index(store, index_path)
    partial.unlink(missing_ok=True)
    return len(chunks)


class Retriever:
    """Recherche sémantique dans l'index chargé depuis le disque."""

    def __init__(self, store: InMemoryVectorStore, top_k: int) -> None:
        self._store = store
        self._top_k = top_k

    @classmethod
    def from_file(cls, index_path: Path, embeddings: Embeddings, top_k: int) -> "Retriever":
        return cls(load_index(index_path, embeddings), top_k)

    async def search(self, question: str) -> list[Document]:
        # Les `top_k` chunks dont l'embedding est le plus proche de celui de la question.
        return await self._store.asimilarity_search(question, k=self._top_k)


def format_context(docs: list[Document]) -> str:
    """Met les chunks en forme pour le prompt, avec la page pour que le LLM puisse la citer."""
    return "\n\n".join(f"[page {d.metadata.get('page', '?')}]\n{d.page_content}" for d in docs)
