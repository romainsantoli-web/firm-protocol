"""Tests for firm.bounty.hackerone — HackerOne API client.

All HTTP calls are mocked — no real API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from firm.bounty.hackerone import HackerOneClient
from firm.bounty.vulnerability import Vulnerability, VulnSeverity


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HACKERONE_API_USERNAME", "test-user")
    monkeypatch.setenv("HACKERONE_API_TOKEN", "test-token")
    return HackerOneClient()


class TestClientConstruction:
    def test_missing_credentials_raises(self, monkeypatch):
        monkeypatch.delenv("HACKERONE_API_USERNAME", raising=False)
        monkeypatch.delenv("HACKERONE_API_TOKEN", raising=False)
        with pytest.raises(ValueError, match="credentials required"):
            HackerOneClient()

    def test_explicit_credentials(self):
        c = HackerOneClient(username="u", token="t")
        assert c.username == "u"
        assert c.token == "t"


class TestListPrograms:
    @patch("firm.bounty.hackerone.httpx.Client")
    def test_list_programs(self, MockClient, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"id": "1", "type": "program"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_resp
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = client.list_programs()
        assert len(result) == 1
        assert result[0]["type"] == "program"


class TestGetScope:
    @patch("firm.bounty.hackerone.httpx.Client")
    def test_get_scope_parses(self, MockClient, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {
                    "attributes": {
                        "asset_identifier": "example.com",
                        "asset_type": "DOMAIN",
                        "eligible_for_bounty": True,
                        "eligible_for_submission": True,
                    }
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_resp
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client_instance

        scope = client.get_scope("test-prog")
        assert len(scope.in_scope) == 1
        assert scope.in_scope[0].identifier == "example.com"


class TestSubmitReport:
    @patch("firm.bounty.hackerone.httpx.Client")
    def test_submit_report(self, MockClient, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"id": "report-123"}}
        mock_resp.raise_for_status = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_resp
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client_instance

        v = Vulnerability(
            title="SQLi",
            description="SQL injection found.",
            severity=VulnSeverity.HIGH,
            cwe_id=89,
            asset="example.com",
        )
        result = client.submit_report("test-prog", v)
        assert result["id"] == "report-123"
