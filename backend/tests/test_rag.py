import hashlib

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from app.core.chat import SYSTEM_PROMPT, ChatService, _search_query
from app.core.models import Message
from app.core.rag import Retriever, format_context, load_index, save_index, split_documents
from tests.test_chat import FakeProvider


class FakeEmbeddings(Embeddings):
    """Embeddings factices et déterministes (hash du texte) : pas d'appel réseau."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [b / 255 for b in hashlib.sha256(text.encode()).digest()]


EMBEDDINGS = FakeEmbeddings()


def make_retriever(tmp_path) -> Retriever:
    store = InMemoryVectorStore(EMBEDDINGS)
    store.add_documents(
        [
            Document(page_content="Les émissions de CO2 de TotalEnergies", metadata={"page": 12}),
            Document(page_content="Le dividende proposé par action", metadata={"page": 40}),
        ]
    )
    # Aller-retour disque : vérifie aussi la sauvegarde/chargement de l'index.
    path = tmp_path / "index.json"
    store.dump(str(path))
    return Retriever.from_file(path, EMBEDDINGS, top_k=1)


def test_split_documents_keeps_page_metadata():
    pages = [Document(page_content="mot " * 600, metadata={"page": 7})]
    chunks = split_documents(pages)
    assert len(chunks) > 1
    assert all(c.metadata["page"] == 7 for c in chunks)


def test_format_context_includes_page():
    docs = [Document(page_content="texte", metadata={"page": 3})]
    assert format_context(docs) == "[page 3]\ntexte"


async def test_retriever_returns_closest_chunk(tmp_path):
    retriever = make_retriever(tmp_path)
    # Même texte que le chunk -> embedding identique -> il est forcément le plus proche.
    docs = await retriever.search("Le dividende proposé par action")
    assert [d.metadata["page"] for d in docs] == [40]


async def test_chat_injects_context_into_system_prompt(tmp_path):
    provider = FakeProvider("ok")
    service = ChatService(provider, make_retriever(tmp_path))
    await service.reply([Message("user", "Le dividende proposé par action")])
    system_prompt = provider.calls[0][0]
    assert system_prompt.startswith(SYSTEM_PROMPT)
    assert "[page 40]" in system_prompt


async def test_chat_without_retriever_keeps_plain_prompt():
    provider = FakeProvider("ok")
    await ChatService(provider).reply([Message("user", "Salut")])
    assert provider.calls[0][0] == SYSTEM_PROMPT


def test_search_query_completes_short_follow_up_with_previous_question():
    messages = [
        Message("user", "Quel est le résultat net en 2025 ?"),
        Message("assistant", "13 127 M$"),
        Message("user", "Et par rapport à 2024 ?"),
    ]
    assert _search_query(messages) == "Quel est le résultat net en 2025 ? Et par rapport à 2024 ?"


def test_search_query_keeps_long_or_first_question_unchanged():
    long_question = "Quels sont les objectifs de réduction des émissions de GES du groupe ?"
    assert (
        _search_query([Message("user", "Salut"), Message("user", long_question)]) == long_question
    )
    assert _search_query([Message("user", "Et en 2024 ?")]) == "Et en 2024 ?"


def test_save_and_load_index_roundtrip_gz(tmp_path):
    store = InMemoryVectorStore(EMBEDDINGS)
    store.add_documents(
        [Document(page_content="Le dividende proposé par action", metadata={"page": 40})]
    )
    path = tmp_path / "index.json.gz"
    save_index(store, path)
    loaded = load_index(path, EMBEDDINGS)
    (entry,) = loaded.store.values()
    assert entry["text"] == "Le dividende proposé par action"
    assert entry["metadata"] == {"page": 40}
    assert len(entry["vector"]) == len(next(iter(store.store.values()))["vector"])
