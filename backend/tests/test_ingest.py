import json

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from app.core.rag import MAX_RETRIES, DailyQuotaExceeded, build_index, load_chunks, load_index


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Les pauses entre lots/tentatives sont réelles en prod ; inutiles dans les tests."""
    monkeypatch.setattr("app.core.rag.time.sleep", lambda _seconds: None)


class ControllableEmbeddings(Embeddings):
    """Embeddings factices : échoue `fail_times` fois puis réussit. Compte les appels."""

    def __init__(self, fail_times: int = 0, daily: bool = False) -> None:
        self.fail_times = fail_times
        self.daily = daily
        self.calls = 0
        self.batch_sizes: list[int] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            suffix = "PerDay" if self.daily else "PerMinute"
            raise Exception(f"429 RESOURCE_EXHAUSTED ({suffix})")
        self.batch_sizes.append(len(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


def make_chunks(n: int) -> list[Document]:
    return [Document(page_content=f"chunk {i}", metadata={"page": i}) for i in range(n)]


def test_build_index_retries_on_per_minute_quota_then_succeeds(tmp_path):
    embeddings = ControllableEmbeddings(fail_times=2)
    count = build_index(make_chunks(5), [embeddings], tmp_path / "index.json")
    assert count == 5
    assert embeddings.calls == 3  # 2 échecs + 1 succès


def test_build_index_raises_after_max_retries(tmp_path):
    embeddings = ControllableEmbeddings(fail_times=MAX_RETRIES + 5)
    with pytest.raises(Exception, match="RESOURCE_EXHAUSTED"):
        build_index(make_chunks(5), [embeddings], tmp_path / "index.json")
    assert embeddings.calls == MAX_RETRIES


def test_build_index_rotates_to_next_key_on_daily_quota(tmp_path):
    exhausted_key = ControllableEmbeddings(fail_times=1, daily=True)
    fresh_key = ControllableEmbeddings()
    count = build_index(make_chunks(5), [exhausted_key, fresh_key], tmp_path / "index.json")
    assert count == 5
    assert exhausted_key.calls == 1
    assert fresh_key.calls == 1
    assert fresh_key.batch_sizes == [5]


def test_build_index_raises_daily_quota_when_no_key_left(tmp_path):
    embeddings = ControllableEmbeddings(fail_times=1, daily=True)
    with pytest.raises(DailyQuotaExceeded):
        build_index(make_chunks(5), [embeddings], tmp_path / "index.json")


def test_build_index_resumes_from_partial_without_re_embedding_done_chunks(tmp_path):
    index_path = tmp_path / "index.json"
    partial_path = index_path.with_name(index_path.name + ".partial")

    # Simule un arrêt après les 3 premiers chunks : on écrit directement le `.partial`.
    seed_store_embeddings = ControllableEmbeddings()
    seed_store = InMemoryVectorStore(seed_store_embeddings)
    seed_store.add_documents(make_chunks(3))
    with partial_path.open("w", encoding="utf-8") as f:
        for entry in seed_store.store.values():
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    resuming_embeddings = ControllableEmbeddings()
    count = build_index(make_chunks(5), [resuming_embeddings], index_path)

    assert count == 5
    # Seuls les 2 chunks manquants sont (ré)embeddés, pas les 3 déjà faits.
    assert resuming_embeddings.batch_sizes == [2]
    assert not partial_path.exists()

    loaded = load_index(index_path, resuming_embeddings)
    assert len(loaded.store) == 5


def test_load_chunks_reads_jsonl_with_page_metadata(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(
        '{"id": "a", "page": 1, "text": "Bonjour"}\n'
        '{"id": "b", "page": 2, "text": "Salut"}\n',
        encoding="utf-8",
    )
    docs = load_chunks(chunks_path)
    assert [d.page_content for d in docs] == ["Bonjour", "Salut"]
    assert [d.metadata["page"] for d in docs] == [1, 2]
