import pytest
from storage.database import Database
from storage.repositories import Repositories
from poetry.collector import PoemCollector
from poetry.poem_analyzer import PoemAnalyzer
from poetry.duplicate_checker import DuplicateChecker


@pytest.fixture
def repos(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return Repositories(db)


def test_collect_preserves_original_and_detects_duplicate(repos):
    collector = PoemCollector(repos)
    text = "Rain on the quiet river\nA flower waits"
    first = collector.collect(text, "en")
    second = collector.collect(text, "en")
    assert first["saved"] and first["text"] == text
    assert second["duplicate"]


def test_analysis_reports_uncertainty():
    result = PoemAnalyzer().analyze("မိုးရွာ ပန်းပွင့်", "my")
    assert result["language"] == "my"
    assert result["confidence"] < .5
    assert result["warning"]


def test_duplicate_exact_and_similarity(repos):
    collector = PoemCollector(repos)
    record = collector.collect("one two three", "en")
    checker = DuplicateChecker(repos)
    assert checker.exact(record["fingerprint"])
    assert checker.similar("one two three")[0][0] == record["id"]
