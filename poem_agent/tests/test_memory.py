from storage.database import Database
from storage.repositories import Repositories
from memory.memory_manager import MemoryManager
from memory.vector_store import VectorStore
from memory.knowledge_base import KnowledgeBase


def test_memory_owner_scope_correction_and_delete(tmp_path):
    db = Database(str(tmp_path / "memory.db")); db.initialize()
    memory = MemoryManager(Repositories(db))
    ident = memory.remember(1, "preference", "Burmese poems", .8, "owner")
    assert len(memory.recall(1)) == 1
    assert memory.recall(2) == []
    assert memory.correct(1, ident, "English poems")
    assert memory.recall(1)[0]["content"] == "English poems"
    assert memory.forget(1, ident)


def test_vector_store_and_knowledge_sources():
    vectors = VectorStore(); vectors.add("a", "poem", [1.0, 0.0])
    assert vectors.search([1.0, 0.0])[0][0] == "a"
    kb = KnowledgeBase(); kb.put("author", "unknown", "owner note", .4)
    assert kb.get("author")["source"] == "owner note"
