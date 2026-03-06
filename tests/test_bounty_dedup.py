"""Tests for firm.bounty.dedup — deduplication engine.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

import pytest

from firm.bounty.dedup import DeduplicationEngine
from firm.bounty.vulnerability import VulnDatabase, Vulnerability


@pytest.fixture
def dedup():
    db = VulnDatabase()
    return DeduplicationEngine(db), db


class TestDedup:
    def test_unique_finding(self, dedup):
        engine, db = dedup
        v = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        result = engine.check_and_add(v)
        assert not result.is_duplicate
        assert result.level == 0

    def test_exact_duplicate_level1(self, dedup):
        engine, db = dedup
        v1 = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        v2 = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        engine.check_and_add(v1)
        result = engine.check_and_add(v2)
        assert result.is_duplicate
        assert result.level == 1

    def test_fuzzy_duplicate_level2(self, dedup):
        engine, db = dedup
        v1 = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        engine.check_and_add(v1)
        # Same CWE + asset, different endpoint
        v2 = Vulnerability(cwe_id=79, asset="a.com", endpoint="/y", parameter="p")
        result = engine.check(v2)
        assert result.is_duplicate
        assert result.level == 2

    def test_different_cwe_not_duplicate(self, dedup):
        engine, db = dedup
        v1 = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        engine.check_and_add(v1)
        v2 = Vulnerability(cwe_id=89, asset="a.com", endpoint="/y", parameter="p")
        result = engine.check(v2)
        assert not result.is_duplicate

    def test_check_only_does_not_persist(self, dedup):
        engine, db = dedup
        v = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        engine.check(v)
        assert db.get(v.id) is None

    def test_check_and_add_persists(self, dedup):
        engine, db = dedup
        v = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        engine.check_and_add(v)
        assert db.get(v.id) is not None
