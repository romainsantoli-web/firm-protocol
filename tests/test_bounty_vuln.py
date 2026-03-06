"""Tests for firm.bounty.vulnerability — CVSS 3.1 + Vulnerability + SQLite DB.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""


from firm.bounty.vulnerability import (
    AttackComplexity,
    AttackVector,
    CVSSVector,
    Impact,
    PrivilegesRequired,
    Scope,
    UserInteraction,
    VulnDatabase,
    Vulnerability,
    VulnSeverity,
)

# ---------------------------------------------------------------------------
# CVSS 3.1
# ---------------------------------------------------------------------------

class TestCVSSVector:
    def test_all_none_impact_zero(self):
        v = CVSSVector()
        assert v.base_score == 0.0

    def test_critical_vector(self):
        """CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H → 10.0"""
        v = CVSSVector(
            attack_vector=AttackVector.NETWORK,
            attack_complexity=AttackComplexity.LOW,
            privileges_required=PrivilegesRequired.NONE,
            user_interaction=UserInteraction.NONE,
            scope=Scope.CHANGED,
            confidentiality=Impact.HIGH,
            integrity=Impact.HIGH,
            availability=Impact.HIGH,
        )
        assert v.base_score == 10.0

    def test_medium_vector(self):
        """CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:U/C:L/I:L/A:N → ~4.6"""
        v = CVSSVector(
            attack_vector=AttackVector.NETWORK,
            attack_complexity=AttackComplexity.LOW,
            privileges_required=PrivilegesRequired.LOW,
            user_interaction=UserInteraction.REQUIRED,
            scope=Scope.UNCHANGED,
            confidentiality=Impact.LOW,
            integrity=Impact.LOW,
            availability=Impact.NONE,
        )
        score = v.base_score
        assert 4.0 <= score <= 5.0

    def test_vector_string(self):
        v = CVSSVector()
        assert v.vector_string.startswith("CVSS:3.1/")

    def test_physical_low_score(self):
        v = CVSSVector(
            attack_vector=AttackVector.PHYSICAL,
            attack_complexity=AttackComplexity.HIGH,
            privileges_required=PrivilegesRequired.HIGH,
            user_interaction=UserInteraction.REQUIRED,
            scope=Scope.UNCHANGED,
            confidentiality=Impact.LOW,
            integrity=Impact.NONE,
            availability=Impact.NONE,
        )
        assert v.base_score < 2.0


# ---------------------------------------------------------------------------
# VulnSeverity
# ---------------------------------------------------------------------------

class TestVulnSeverity:
    def test_from_score_critical(self):
        assert VulnSeverity.from_score(9.5) == VulnSeverity.CRITICAL

    def test_from_score_high(self):
        assert VulnSeverity.from_score(7.5) == VulnSeverity.HIGH

    def test_from_score_medium(self):
        assert VulnSeverity.from_score(5.0) == VulnSeverity.MEDIUM

    def test_from_score_low(self):
        assert VulnSeverity.from_score(2.0) == VulnSeverity.LOW

    def test_from_score_info(self):
        assert VulnSeverity.from_score(0.0) == VulnSeverity.INFO


# ---------------------------------------------------------------------------
# Vulnerability
# ---------------------------------------------------------------------------

class TestVulnerability:
    def test_fingerprint_deterministic(self):
        v1 = Vulnerability(cwe_id=79, asset="example.com", endpoint="/xss", parameter="q")
        v2 = Vulnerability(cwe_id=79, asset="example.com", endpoint="/xss", parameter="q")
        assert v1.fingerprint == v2.fingerprint

    def test_fingerprint_differs(self):
        v1 = Vulnerability(cwe_id=79, asset="example.com", endpoint="/xss", parameter="q")
        v2 = Vulnerability(cwe_id=89, asset="example.com", endpoint="/xss", parameter="q")
        assert v1.fingerprint != v2.fingerprint

    def test_to_markdown_report(self):
        v = Vulnerability(
            title="Reflected XSS",
            description="Input not sanitised.",
            cwe_id=79,
            severity=VulnSeverity.MEDIUM,
            asset="example.com",
            endpoint="/search",
        )
        md = v.to_markdown_report()
        assert "# Reflected XSS" in md
        assert "CWE-79" in md
        assert "MEDIUM" in md

    def test_update_severity_from_cvss(self):
        v = Vulnerability(
            cvss=CVSSVector(
                attack_vector=AttackVector.NETWORK,
                attack_complexity=AttackComplexity.LOW,
                privileges_required=PrivilegesRequired.NONE,
                user_interaction=UserInteraction.NONE,
                scope=Scope.CHANGED,
                confidentiality=Impact.HIGH,
                integrity=Impact.HIGH,
                availability=Impact.HIGH,
            ),
        )
        v.update_severity_from_cvss()
        assert v.severity == VulnSeverity.CRITICAL

    def test_to_dict_and_from_dict(self):
        v = Vulnerability(title="Test", cwe_id=89, asset="a.com")
        d = v.to_dict()
        v2 = Vulnerability.from_dict(d)
        assert v2.title == "Test"
        assert v2.cwe_id == 89


# ---------------------------------------------------------------------------
# VulnDatabase
# ---------------------------------------------------------------------------

class TestVulnDatabase:
    def test_insert_and_get(self):
        with VulnDatabase() as db:
            v = Vulnerability(title="SQLi", cwe_id=89, asset="x.com")
            db.insert(v)
            got = db.get(v.id)
            assert got is not None
            assert got.title == "SQLi"

    def test_find_by_fingerprint(self):
        with VulnDatabase() as db:
            v = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="p")
            db.insert(v)
            hits = db.find_by_fingerprint(v.fingerprint)
            assert len(hits) == 1

    def test_search_by_severity(self):
        with VulnDatabase() as db:
            db.insert(Vulnerability(title="A", severity=VulnSeverity.HIGH, asset="a.com"))
            db.insert(Vulnerability(title="B", severity=VulnSeverity.LOW, asset="a.com"))
            results = db.search(severity="high")
            assert len(results) == 1
            assert results[0].title == "A"

    def test_search_by_asset(self):
        with VulnDatabase() as db:
            db.insert(Vulnerability(title="A", asset="target.com"))
            db.insert(Vulnerability(title="B", asset="other.com"))
            results = db.search(asset="target")
            assert len(results) == 1

    def test_stats(self):
        with VulnDatabase() as db:
            db.insert(Vulnerability(severity=VulnSeverity.CRITICAL, bounty_amount=500))
            db.insert(Vulnerability(severity=VulnSeverity.HIGH, bounty_amount=200))
            s = db.stats()
            assert s["total"] == 2
            assert s["critical"] == 1
            assert s["total_bounty"] == 700.0

    def test_get_nonexistent(self):
        with VulnDatabase() as db:
            assert db.get("nonexistent-id") is None
