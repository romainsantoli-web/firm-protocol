"""
Tests for firm.core.serialization — Save / Load FIRM State
"""

import json
import time

from firm.core.serialization import (
    SERIALIZATION_VERSION,
    diff_snapshots,
    load_firm,
    save_firm,
    snapshot,
)
from firm.runtime import Firm

# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_firm() -> Firm:
    """Create a FIRM with agents, memories, and roles for testing."""
    firm = Firm(name="serial-test")
    firm.add_agent("ceo", authority=0.9)
    dev = firm.add_agent("dev", authority=0.5)

    # Add a role
    firm.define_role("engineer", min_authority=0.3, description="Builds stuff")
    firm.assign_role(dev.id, "engineer")

    # Record some actions
    firm.record_action(dev.id, success=True, description="shipped feature")
    firm.record_action(dev.id, success=True, description="fixed bug")

    # Contribute memory
    firm.memory.contribute(
        content="Python is the best language for prototyping",
        tags=["python", "prototyping"],
        contributor_id=dev.id,
        contributor_authority=dev.authority,
    )

    return firm


# ── save_firm ────────────────────────────────────────────────────────────────


class TestSaveFirm:
    """Tests for save_firm()."""

    def test_save_returns_dict(self):
        firm = Firm(name="save-test")
        state = save_firm(firm)
        assert isinstance(state, dict)
        assert state["name"] == "save-test"

    def test_save_includes_version(self):
        state = save_firm(Firm(name="v"))
        assert state["_version"] == SERIALIZATION_VERSION

    def test_save_includes_timestamp(self):
        before = time.time()
        state = save_firm(Firm(name="t"))
        after = time.time()
        assert before <= state["_saved_at"] <= after

    def test_save_includes_agents(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert len(state["agents"]) == 2
        names = {a["name"] for a in state["agents"].values()}
        assert names == {"ceo", "dev"}

    def test_save_agent_fields(self):
        firm = _build_firm()
        state = save_firm(firm)
        dev_data = [a for a in state["agents"].values() if a["name"] == "dev"][0]
        assert "authority" in dev_data
        assert "credits" in dev_data
        assert "status" in dev_data
        assert "roles" in dev_data
        assert "engineer" in dev_data["roles"]

    def test_save_includes_memories(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert state["memory"]["total_entries"] == 1
        assert len(state["memory"]["entries"]) == 1
        mem = state["memory"]["entries"][0]
        assert "python" in mem["tags"]
        assert mem["content"] == "Python is the best language for prototyping"

    def test_save_includes_ledger(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert state["ledger"]["length"] > 0
        assert len(state["ledger"]["entries"]) > 0

    def test_save_includes_roles(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert len(state["roles"]) >= 1
        eng = [r for r in state["roles"] if r["name"] == "engineer"][0]
        assert eng["min_authority"] == 0.3

    def test_save_includes_constitution(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert "constitution" in state
        assert "kill_switch_active" in state["constitution"]

    def test_save_to_file(self, tmp_path):
        firm = _build_firm()
        path = tmp_path / "firm.json"
        save_firm(firm, path)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["name"] == "serial-test"

    def test_save_creates_parent_dirs(self, tmp_path):
        firm = Firm(name="nested")
        path = tmp_path / "deep" / "nested" / "firm.json"
        save_firm(firm, path)
        assert path.exists()

    def test_save_includes_evolution_stats(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert "evolution" in state

    def test_save_includes_market_stats(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert "market" in state

    def test_save_includes_federation_stats(self):
        firm = _build_firm()
        state = save_firm(firm)
        assert "federation" in state


# ── load_firm ────────────────────────────────────────────────────────────────


class TestLoadFirm:
    """Tests for load_firm()."""

    def test_load_from_dict(self):
        firm = _build_firm()
        state = save_firm(firm)
        restored = load_firm(state)
        assert restored.name == "serial-test"

    def test_load_restores_agents(self):
        firm = _build_firm()
        state = save_firm(firm)
        restored = load_firm(state)
        agents = restored.get_agents(active_only=False)
        assert len(agents) == 2
        names = {a.name for a in agents}
        assert names == {"ceo", "dev"}

    def test_load_restores_authority(self):
        firm = _build_firm()
        dev = [a for a in firm.get_agents() if a.name == "dev"][0]
        original_auth = dev.authority
        state = save_firm(firm)
        restored = load_firm(state)
        dev2 = [a for a in restored.get_agents() if a.name == "dev"][0]
        assert abs(dev2.authority - original_auth) < 0.0001

    def test_load_restores_roles(self):
        firm = _build_firm()
        state = save_firm(firm)
        restored = load_firm(state)
        dev2 = [a for a in restored.get_agents() if a.name == "dev"][0]
        role_names = [r.name for r in dev2.roles]
        assert "engineer" in role_names

    def test_load_restores_memories(self):
        firm = _build_firm()
        state = save_firm(firm)
        restored = load_firm(state)
        memories = restored.memory.get_all()
        assert len(memories) == 1
        assert "python" in memories[0].tags

    def test_load_restores_recall(self):
        """Memory tag index should be rebuilt so recall works."""
        firm = _build_firm()
        state = save_firm(firm)
        restored = load_firm(state)
        results = restored.memory.recall(tags=["python"])
        assert len(results) >= 1
        assert "prototyping" in results[0].content.lower()

    def test_load_restores_firm_id(self):
        firm = _build_firm()
        state = save_firm(firm)
        restored = load_firm(state)
        assert restored.id == firm.id

    def test_load_restores_authority_config(self):
        firm = Firm(name="auth-cfg", learning_rate=0.1, decay=0.05)
        state = save_firm(firm)
        restored = load_firm(state)
        assert restored.authority.learning_rate == 0.1
        assert restored.authority.decay == 0.05

    def test_load_from_file(self, tmp_path):
        firm = _build_firm()
        path = tmp_path / "firm.json"
        save_firm(firm, path)
        restored = load_firm(str(path))
        assert restored.name == "serial-test"
        assert len(restored.get_agents(active_only=False)) == 2

    def test_load_version_mismatch_warns(self, caplog):
        firm = Firm(name="vwarn")
        state = save_firm(firm)
        state["_version"] = "99.0.0"
        import logging
        with caplog.at_level(logging.WARNING, logger="firm.core.serialization"):
            load_firm(state)
        assert "mismatch" in caplog.text.lower()

    def test_load_restores_kill_switch(self):
        firm = Firm(name="killsw")
        firm.constitution.activate_kill_switch(reason="test")
        state = save_firm(firm)
        restored = load_firm(state)
        assert restored.constitution.kill_switch_active is True


# ── Round-trip ───────────────────────────────────────────────────────────────


class TestRoundTrip:
    """Save → load → save should produce equivalent state."""

    def test_roundtrip_agent_count(self):
        firm = _build_firm()
        s1 = save_firm(firm)
        restored = load_firm(s1)
        s2 = save_firm(restored)
        assert len(s1["agents"]) == len(s2["agents"])

    def test_roundtrip_memory_count(self):
        firm = _build_firm()
        s1 = save_firm(firm)
        restored = load_firm(s1)
        s2 = save_firm(restored)
        assert s1["memory"]["total_entries"] == s2["memory"]["total_entries"]

    def test_roundtrip_role_count(self):
        firm = _build_firm()
        s1 = save_firm(firm)
        restored = load_firm(s1)
        s2 = save_firm(restored)
        assert len(s1["roles"]) == len(s2["roles"])

    def test_roundtrip_via_file(self, tmp_path):
        firm = _build_firm()
        path = tmp_path / "rt.json"
        save_firm(firm, path)
        restored = load_firm(path)
        assert restored.name == firm.name
        assert len(restored.get_agents(active_only=False)) == 2


# ── snapshot ─────────────────────────────────────────────────────────────────


class TestSnapshot:
    """Tests for snapshot()."""

    def test_snapshot_returns_state(self):
        firm = _build_firm()
        snap = snapshot(firm)
        assert snap["name"] == "serial-test"
        assert "_version" in snap

    def test_snapshot_via_firm_method(self):
        firm = _build_firm()
        snap = firm.snapshot()
        assert snap["name"] == "serial-test"

    def test_snapshot_is_independent_copy(self):
        """Modifying the firm after snapshot shouldn't affect snapshot."""
        firm = Firm(name="snap")
        snap1 = snapshot(firm)
        firm.add_agent("new-agent", authority=0.5)
        snap2 = snapshot(firm)
        assert len(snap1["agents"]) < len(snap2["agents"])


# ── diff_snapshots ───────────────────────────────────────────────────────────


class TestDiffSnapshots:
    """Tests for diff_snapshots()."""

    def test_diff_detects_added_agent(self):
        firm = Firm(name="diff")
        s1 = snapshot(firm)
        firm.add_agent("new", authority=0.5)
        s2 = snapshot(firm)
        diff = diff_snapshots(s1, s2)
        assert diff["agents_added"] == 1

    def test_diff_detects_authority_change(self):
        firm = Firm(name="diff")
        a = firm.add_agent("dev", authority=0.5)
        s1 = snapshot(firm)
        firm.record_action(a.id, success=True, description="good work")
        s2 = snapshot(firm)
        diff = diff_snapshots(s1, s2)
        assert "authority_changes" in diff
        assert len(diff["authority_changes"]) >= 1

    def test_diff_detects_ledger_growth(self):
        firm = Firm(name="diff")
        a = firm.add_agent("dev", authority=0.5)
        s1 = snapshot(firm)
        firm.record_action(a.id, success=True, description="action")
        s2 = snapshot(firm)
        diff = diff_snapshots(s1, s2)
        assert diff["ledger_entries_added"] > 0

    def test_diff_detects_memory_change(self):
        firm = Firm(name="diff")
        a = firm.add_agent("dev", authority=0.5)
        s1 = snapshot(firm)
        firm.memory.contribute(
            content="new info",
            tags=["test"],
            contributor_id=a.id,
            contributor_authority=a.authority,
        )
        s2 = snapshot(firm)
        diff = diff_snapshots(s1, s2)
        assert diff["memories_added"] == 1

    def test_diff_includes_timestamps(self):
        s1 = snapshot(Firm(name="a"))
        s2 = snapshot(Firm(name="b"))
        diff = diff_snapshots(s1, s2)
        assert "_snapshot_time_before" in diff
        assert "_snapshot_time_after" in diff

    def test_diff_identical_snapshots(self):
        firm = Firm(name="same")
        s = snapshot(firm)
        diff = diff_snapshots(s, s)
        # Should have timestamps but no changes
        assert "agents_added" not in diff
        assert "authority_changes" not in diff
        assert "ledger_entries_added" not in diff

    def test_diff_constitution_invariant_change(self):
        """Track invariant count changes between two different firms."""
        from firm.core.constitution import ALL_INVARIANTS, Invariant

        firm1 = Firm(name="const1")
        s1 = snapshot(firm1)

        extra_inv = Invariant(id="INV-99", description="No spam", violation_keywords=("spam",))
        firm2 = Firm(name="const2")
        firm2.constitution.invariants = ALL_INVARIANTS + (extra_inv,)
        s2 = snapshot(firm2)

        diff = diff_snapshots(s1, s2)
        assert diff.get("invariants_changed", 0) == 1


# ── Firm.save / Firm.load convenience ────────────────────────────────────────


class TestFirmConvenience:
    """Tests for Firm.save() and Firm.load() shortcut methods."""

    def test_firm_save(self):
        firm = _build_firm()
        state = firm.save()
        assert state["name"] == "serial-test"

    def test_firm_load(self):
        firm = _build_firm()
        state = firm.save()
        restored = Firm.load(state)
        assert restored.name == "serial-test"

    def test_firm_save_to_file(self, tmp_path):
        firm = _build_firm()
        path = tmp_path / "firm.json"
        firm.save(str(path))
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "serial-test"

    def test_firm_load_from_file(self, tmp_path):
        firm = _build_firm()
        path = tmp_path / "firm.json"
        firm.save(str(path))
        restored = Firm.load(str(path))
        assert restored.name == "serial-test"
