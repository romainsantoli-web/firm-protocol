"""Tests for firm.bounty.scope — scope enforcement.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

import pytest

from firm.bounty.scope import Asset, AssetType, ScopeEnforcer, TargetScope

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def basic_scope():
    return TargetScope(
        programme_name="Test Program",
        programme_handle="test-prog",
        in_scope=[
            Asset("example.com", AssetType.DOMAIN),
            Asset("*.example.com", AssetType.WILDCARD),
            Asset("192.0.2.0/24", AssetType.CIDR),
            Asset("api.target.io", AssetType.URL),
        ],
        out_of_scope=[
            Asset("internal.example.com", AssetType.DOMAIN),
            Asset("192.0.2.1", AssetType.IP_ADDRESS),
        ],
    )


@pytest.fixture
def enforcer(basic_scope):
    return ScopeEnforcer(basic_scope)


# ---------------------------------------------------------------------------
# Asset matching
# ---------------------------------------------------------------------------

class TestAsset:
    def test_domain_match_exact(self):
        a = Asset("example.com", AssetType.DOMAIN)
        assert a.matches_domain("example.com")
        assert not a.matches_domain("other.com")

    def test_domain_match_subdomain(self):
        a = Asset("example.com", AssetType.DOMAIN)
        assert a.matches_domain("sub.example.com")

    def test_wildcard_match(self):
        a = Asset("*.example.com", AssetType.WILDCARD)
        assert a.matches_domain("app.example.com")
        assert a.matches_domain("deep.sub.example.com")
        assert a.matches_domain("example.com")  # base domain matches wildcard
        assert not a.matches_domain("other.com")

    def test_cidr_match(self):
        a = Asset("192.0.2.0/24", AssetType.CIDR)
        assert a.matches_ip("192.0.2.100")
        assert not a.matches_ip("192.0.3.1")

    def test_ip_match(self):
        a = Asset("203.0.113.5", AssetType.IP_ADDRESS)
        assert a.matches_ip("203.0.113.5")
        assert not a.matches_ip("203.0.113.6")

    def test_invalid_ip(self):
        a = Asset("192.0.2.0/24", AssetType.CIDR)
        assert not a.matches_ip("not-an-ip")


# ---------------------------------------------------------------------------
# Scope enforcer
# ---------------------------------------------------------------------------

class TestScopeEnforcer:
    def test_allow_in_scope_domain(self, enforcer):
        assert enforcer.allow_host("example.com")
        assert enforcer.allow_host("app.example.com")

    def test_block_out_of_scope(self, enforcer):
        assert not enforcer.allow_host("internal.example.com")

    def test_block_out_of_scope_ip(self, enforcer):
        assert not enforcer.allow_host("192.0.2.1")

    def test_allow_in_scope_cidr(self, enforcer):
        assert enforcer.allow_host("192.0.2.50")

    def test_block_private_ip(self, enforcer):
        assert not enforcer.allow_host("127.0.0.1")
        assert not enforcer.allow_host("10.0.0.1")
        assert not enforcer.allow_host("172.16.0.1")
        assert not enforcer.allow_host("192.168.1.1")
        assert not enforcer.allow_host("169.254.169.254")  # AWS metadata

    def test_block_ipv6_loopback(self, enforcer):
        assert not enforcer.allow_host("::1")

    def test_allow_url_in_scope(self, enforcer):
        assert enforcer.allow_url("https://app.example.com/api/v1")
        assert enforcer.allow_url("http://api.target.io/login")

    def test_block_url_out_of_scope(self, enforcer):
        assert not enforcer.allow_url("https://evil.com/phish")
        assert not enforcer.allow_url("http://127.0.0.1:8080/admin")

    def test_block_url_no_host(self, enforcer):
        assert not enforcer.allow_url("")
        assert not enforcer.allow_url("not-a-url")

    def test_allow_command(self, enforcer):
        assert enforcer.allow_command("nmap -sS example.com")
        assert enforcer.allow_command("nuclei -u https://app.example.com")

    def test_block_command_off_target(self, enforcer):
        assert not enforcer.allow_command("nmap -sS evil.com")

    def test_block_command_no_target(self, enforcer):
        assert not enforcer.allow_command("ls -la")

    def test_block_not_in_scope(self, enforcer):
        assert not enforcer.allow_host("random-site.org")


# ---------------------------------------------------------------------------
# TargetScope builders
# ---------------------------------------------------------------------------

class TestTargetScopeBuilders:
    def test_from_hackerone_dict(self):
        data = {
            "name": "TestProg",
            "handle": "testprog",
            "structured_scopes": [
                {
                    "asset_identifier": "example.com",
                    "asset_type": "domain",
                    "eligible_for_bounty": True,
                    "eligible_for_submission": True,
                },
                {
                    "asset_identifier": "staging.example.com",
                    "asset_type": "domain",
                    "eligible_for_submission": False,
                },
            ],
        }
        scope = TargetScope.from_hackerone_dict(data)
        assert scope.programme_handle == "testprog"
        assert len(scope.in_scope) == 1
        assert len(scope.out_of_scope) == 1
        assert scope.in_scope[0].identifier == "example.com"

    def test_from_yaml(self, tmp_path):
        yaml_content = """
programme_name: "YAML Test"
programme_handle: "yaml-test"
in_scope:
  - identifier: "example.com"
    type: "domain"
    eligible: true
  - identifier: "*.api.example.com"
    type: "wildcard"
out_of_scope:
  - identifier: "staging.example.com"
    type: "domain"
"""
        f = tmp_path / "scope.yaml"
        f.write_text(yaml_content)
        scope = TargetScope.from_yaml(f)
        assert scope.programme_name == "YAML Test"
        assert len(scope.in_scope) == 2
        assert len(scope.out_of_scope) == 1
