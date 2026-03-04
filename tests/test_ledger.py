"""Tests for firm.core.ledger — Responsibility Ledger"""

import pytest

from firm.core.ledger import (
    GENESIS_HASH,
    LedgerEntry,
    ResponsibilityLedger,
)
from firm.core.types import AgentId, LedgerAction


class TestLedgerEntry:
    def test_entry_hash_deterministic(self):
        e1 = LedgerEntry(id="test-1", agent_id=AgentId("a"), timestamp=1000.0)
        e2 = LedgerEntry(id="test-1", agent_id=AgentId("a"), timestamp=1000.0)
        assert e1.compute_hash() == e2.compute_hash()

    def test_entry_hash_changes_with_content(self):
        e1 = LedgerEntry(id="test-1", agent_id=AgentId("a"), timestamp=1000.0)
        e2 = LedgerEntry(id="test-2", agent_id=AgentId("a"), timestamp=1000.0)
        assert e1.compute_hash() != e2.compute_hash()

    def test_seal_sets_hash(self):
        entry = LedgerEntry()
        assert entry.entry_hash == ""
        entry.seal()
        assert len(entry.entry_hash) == 64  # SHA-256 hex

    def test_seal_twice_raises(self):
        entry = LedgerEntry()
        entry.seal()
        with pytest.raises(RuntimeError, match="already sealed"):
            entry.seal()

    def test_verify_valid_entry(self):
        entry = LedgerEntry()
        entry.seal()
        assert entry.verify()

    def test_verify_tampered_entry(self):
        entry = LedgerEntry(description="original")
        entry.seal()
        # Tamper
        entry.description = "tampered"
        assert not entry.verify()

    def test_verify_unsealed(self):
        entry = LedgerEntry()
        assert not entry.verify()

    def test_to_dict(self):
        entry = LedgerEntry(
            id="e1",
            agent_id=AgentId("a1"),
            action=LedgerAction.DECISION,
            description="test",
        )
        entry.seal()
        d = entry.to_dict()
        assert d["id"] == "e1"
        assert d["action"] == "decision"
        assert d["entry_hash"] != ""


class TestResponsibilityLedger:
    def test_empty_ledger(self):
        ledger = ResponsibilityLedger()
        assert ledger.length == 0
        assert ledger.last_hash == GENESIS_HASH

    def test_append_entry(self):
        ledger = ResponsibilityLedger()
        entry = ledger.append(
            agent_id=AgentId("a1"),
            action=LedgerAction.DECISION,
            description="First action",
        )
        assert ledger.length == 1
        assert entry.entry_hash != ""
        assert entry.previous_hash == GENESIS_HASH

    def test_chain_linking(self):
        ledger = ResponsibilityLedger()
        e1 = ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.DECISION, description="First",
        )
        e2 = ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.DECISION, description="Second",
        )
        assert e2.previous_hash == e1.entry_hash

    def test_verify_valid_chain(self):
        ledger = ResponsibilityLedger()
        for i in range(10):
            ledger.append(
                agent_id=AgentId("a1"),
                action=LedgerAction.TASK_COMPLETED,
                description=f"Task {i}",
                credit_delta=5.0,
            )
        result = ledger.verify_chain()
        assert result["valid"]
        assert result["checked"] == 10

    def test_detect_tampered_chain(self):
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.DECISION, description="ok",
        )
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.DECISION, description="ok2",
        )
        # Tamper with first entry
        ledger._entries[0].description = "tampered"
        result = ledger.verify_chain()
        assert not result["valid"]
        assert result["broken_at"] == 0

    def test_credit_tracking(self):
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.TASK_COMPLETED,
            description="earn", credit_delta=50.0,
        )
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.TASK_FAILED,
            description="lose", credit_delta=-20.0,
        )
        assert ledger.get_balance(AgentId("a1")) == 30.0

    def test_balance_per_agent(self):
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.TASK_COMPLETED,
            description="earn", credit_delta=100.0,
        )
        ledger.append(
            agent_id=AgentId("a2"), action=LedgerAction.TASK_COMPLETED,
            description="earn", credit_delta=50.0,
        )
        assert ledger.get_balance(AgentId("a1")) == 100.0
        assert ledger.get_balance(AgentId("a2")) == 50.0
        assert ledger.get_balance(AgentId("a3")) == 0.0

    def test_get_entries_filtered(self):
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.DECISION, description="d1",
        )
        ledger.append(
            agent_id=AgentId("a2"), action=LedgerAction.TASK_COMPLETED, description="t1",
        )
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.TASK_FAILED, description="f1",
        )
        entries_a1 = ledger.get_entries(agent_id=AgentId("a1"))
        assert len(entries_a1) == 2

        entries_tasks = ledger.get_entries(action=LedgerAction.TASK_COMPLETED)
        assert len(entries_tasks) == 1

    def test_agent_summary(self):
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.TASK_COMPLETED,
            description="earn", credit_delta=10.0,
        )
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.TASK_FAILED,
            description="lose", credit_delta=-5.0,
        )
        summary = ledger.get_agent_summary(AgentId("a1"))
        assert summary["total_entries"] == 2
        assert summary["total_credits"] == 5.0

    def test_agent_summary_empty(self):
        ledger = ResponsibilityLedger()
        summary = ledger.get_agent_summary(AgentId("nobody"))
        assert summary["total_entries"] == 0

    def test_stats(self):
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"), action=LedgerAction.TASK_COMPLETED,
            description="earn", credit_delta=100.0,
        )
        ledger.append(
            agent_id=AgentId("a2"), action=LedgerAction.TASK_FAILED,
            description="lose", credit_delta=-30.0,
        )
        stats = ledger.get_stats()
        assert stats["total_entries"] == 2
        assert stats["agents"] == 2
        assert stats["total_credits_earned"] == 100.0
        assert stats["total_credits_spent"] == 30.0
        assert stats["chain_valid"]

    def test_verify_empty_chain(self):
        ledger = ResponsibilityLedger()
        result = ledger.verify_chain()
        assert result["valid"]
        assert result["checked"] == 0
