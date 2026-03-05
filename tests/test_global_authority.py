"""Tests for PredictionAccuracyAttestation and global_authority()."""

import pytest

from firm.core.reputation import (
    PredictionAccuracyAttestation,
    ReputationBridge,
    global_authority,
)
from firm.core.types import AgentId, FirmId


# ── PredictionAccuracyAttestation ────────────────────────────────────────────


class TestPredictionAccuracyAttestation:
    def test_seal_and_verify(self):
        att = PredictionAccuracyAttestation(
            agent_id=AgentId("alice"),
            source_firm=FirmId("firm-1"),
            markets_participated=10,
            avg_brier_score=0.15,
            calibration_score=1.3,
            total_profit=42.5,
        )
        att.seal()
        assert att.attestation_hash != ""
        assert att.verify() is True

    def test_verify_fails_without_seal(self):
        att = PredictionAccuracyAttestation()
        assert att.verify() is False

    def test_tampered_hash_fails(self):
        att = PredictionAccuracyAttestation(
            agent_id=AgentId("bob"),
            source_firm=FirmId("firm-2"),
            markets_participated=5,
        )
        att.seal()
        att.markets_participated = 999
        assert att.verify() is False

    def test_to_dict(self):
        att = PredictionAccuracyAttestation(
            agent_id=AgentId("c"),
            source_firm=FirmId("f"),
            markets_participated=3,
            avg_brier_score=0.12345,
            calibration_score=1.1111,
            total_profit=99.999,
        )
        att.seal()
        d = att.to_dict()
        assert d["avg_brier_score"] == 0.1235
        assert d["calibration_score"] == 1.1111
        assert d["total_profit"] == 100.0
        assert d["attestation_hash"] == att.attestation_hash

    def test_compute_hash_deterministic(self):
        att = PredictionAccuracyAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("f"),
        )
        h1 = att.compute_hash()
        h2 = att.compute_hash()
        assert h1 == h2


# ── global_authority ─────────────────────────────────────────────────────────


class TestGlobalAuthority:
    def test_pure_local(self):
        # G = 0.6*0.8 + 0.25*(0.8*1.0) + 0.15*0 = 0.48 + 0.20 = 0.68
        g = global_authority(0.8, calibration_score=1.0, peer_attestation_sum=0.0)
        assert g == pytest.approx(0.68, abs=0.01)

    def test_good_calibration_boosts(self):
        g_good = global_authority(0.5, calibration_score=1.5)
        g_base = global_authority(0.5, calibration_score=1.0)
        assert g_good > g_base

    def test_poor_calibration_hurts(self):
        g_poor = global_authority(0.5, calibration_score=0.5)
        g_base = global_authority(0.5, calibration_score=1.0)
        assert g_poor < g_base

    def test_peer_attestations_contribute(self):
        g_peers = global_authority(0.5, peer_attestation_sum=0.2)
        g_no = global_authority(0.5, peer_attestation_sum=0.0)
        assert g_peers > g_no

    def test_peer_attestations_capped(self):
        g_mod = global_authority(0.5, peer_attestation_sum=0.3)
        g_exc = global_authority(0.5, peer_attestation_sum=10.0)
        assert g_mod == pytest.approx(g_exc)

    def test_clamped_to_one(self):
        g = global_authority(1.0, calibration_score=2.0, peer_attestation_sum=1.0)
        assert g <= 1.0

    def test_clamped_to_zero(self):
        g = global_authority(0.0, calibration_score=0.1, peer_attestation_sum=0.0)
        assert g >= 0.0

    def test_exact_formula(self):
        # G = 0.6*0.4 + 0.25*(0.4*1.2) + 0.15*min(0.3, 0.1) = 0.24 + 0.12 + 0.015 = 0.375
        g = global_authority(0.4, calibration_score=1.2, peer_attestation_sum=0.1)
        assert g == pytest.approx(0.375, abs=0.001)


# ── ReputationBridge prediction attestation ──────────────────────────────────


class TestReputationBridgePrediction:
    def test_issue_prediction_attestation(self):
        bridge = ReputationBridge(FirmId("test-firm"))
        att = bridge.issue_prediction_attestation(
            agent_id=AgentId("alice"),
            markets_participated=15,
            avg_brier_score=0.12,
            calibration_score=1.4,
            total_profit=100.0,
        )
        assert att.verify()
        assert att.agent_id == "alice"
        assert att.markets_participated == 15

    def test_attestation_in_stats(self):
        bridge = ReputationBridge(FirmId("test-firm"))
        bridge.issue_prediction_attestation(
            agent_id=AgentId("a"),
            markets_participated=1,
            avg_brier_score=0.2,
            calibration_score=1.0,
        )
        stats = bridge.get_stats()
        assert stats["prediction_attestations"] == 1
