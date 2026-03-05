"""
Tests for firm.core.plugins — Plugin / Extension System
"""

import pytest

from firm.core.plugins import FirmPlugin, PluginManager


# ── Helper plugins ───────────────────────────────────────────────────────────


class CounterPlugin(FirmPlugin):
    """Simple plugin that counts events."""

    name = "counter"
    version = "1.0.0"
    description = "Counts actions"

    def __init__(self):
        self.action_count = 0
        self.activated = False
        self.deactivated = False

    def on_activate(self, firm):
        self.activated = True
        firm.events.subscribe("action.recorded", self._on_action)

    def on_deactivate(self, firm):
        self.deactivated = True
        firm.events.unsubscribe("action.recorded", self._on_action)

    def _on_action(self, event):
        self.action_count += 1


class FailingPlugin(FirmPlugin):
    """Plugin that fails on activation."""

    name = "fail-plugin"
    version = "0.1.0"

    def on_activate(self, firm):
        raise RuntimeError("Activation crashed!")


class MinimalPlugin(FirmPlugin):
    """Minimal plugin — only on_activate required."""

    name = "minimal"
    version = "0.0.1"

    def on_activate(self, firm):
        pass


# ── FirmPlugin tests ─────────────────────────────────────────────────────────


class TestFirmPlugin:
    """Tests for the FirmPlugin ABC."""

    def test_get_info(self):
        p = CounterPlugin()
        info = p.get_info()
        assert info["name"] == "counter"
        assert info["version"] == "1.0.0"
        assert info["description"] == "Counts actions"

    def test_default_values(self):
        p = MinimalPlugin()
        assert p.name == "minimal"
        assert p.version == "0.0.1"
        assert p.description == ""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            FirmPlugin()


# ── PluginManager registration ───────────────────────────────────────────────


class TestPluginManagerRegistration:
    """Register / unregister plugins."""

    def test_register(self):
        pm = PluginManager()
        pm.register(CounterPlugin())
        assert "counter" in pm.registered

    def test_register_duplicate_raises(self):
        pm = PluginManager()
        pm.register(CounterPlugin())
        with pytest.raises(ValueError, match="already registered"):
            pm.register(CounterPlugin())

    def test_unregister(self):
        pm = PluginManager()
        pm.register(CounterPlugin())
        assert pm.unregister("counter") is True
        assert "counter" not in pm.registered

    def test_unregister_unknown(self):
        pm = PluginManager()
        assert pm.unregister("nope") is False

    def test_unregister_active_plugin(self):
        """Unregistering an active plugin deactivates it."""
        from firm.runtime import Firm
        pm = PluginManager()
        pm.register(CounterPlugin())
        firm = Firm(name="pm-test")
        pm.activate("counter", firm)
        assert pm.is_active("counter")
        pm.unregister("counter")
        assert not pm.is_active("counter")
        assert "counter" not in pm.registered

    def test_get_plugin(self):
        pm = PluginManager()
        p = CounterPlugin()
        pm.register(p)
        assert pm.get_plugin("counter") is p

    def test_get_plugin_not_found(self):
        pm = PluginManager()
        assert pm.get_plugin("nonexistent") is None


# ── PluginManager activation ─────────────────────────────────────────────────


class TestPluginManagerActivation:
    """Activate / deactivate lifecycle."""

    def _make_firm(self):
        from firm.runtime import Firm
        return Firm(name="plugin-test")

    def test_activate(self):
        pm = PluginManager()
        p = CounterPlugin()
        pm.register(p)
        firm = self._make_firm()
        pm.activate("counter", firm)
        assert pm.is_active("counter")
        assert p.activated is True

    def test_activate_unregistered_raises(self):
        pm = PluginManager()
        firm = self._make_firm()
        with pytest.raises(KeyError, match="not registered"):
            pm.activate("ghost", firm)

    def test_activate_already_active_noop(self):
        pm = PluginManager()
        p = CounterPlugin()
        pm.register(p)
        firm = self._make_firm()
        pm.activate("counter", firm)
        pm.activate("counter", firm)  # second call is noop
        assert pm.is_active("counter")

    def test_activate_failure_propagated(self):
        pm = PluginManager()
        pm.register(FailingPlugin())
        firm = self._make_firm()
        with pytest.raises(RuntimeError, match="crashed"):
            pm.activate("fail-plugin", firm)
        assert not pm.is_active("fail-plugin")

    def test_deactivate(self):
        pm = PluginManager()
        p = CounterPlugin()
        pm.register(p)
        firm = self._make_firm()
        pm.activate("counter", firm)
        pm.deactivate("counter", firm)
        assert not pm.is_active("counter")
        assert p.deactivated is True

    def test_deactivate_unregistered_raises(self):
        pm = PluginManager()
        firm = self._make_firm()
        with pytest.raises(KeyError, match="not registered"):
            pm.deactivate("ghost", firm)

    def test_deactivate_inactive_noop(self):
        pm = PluginManager()
        pm.register(CounterPlugin())
        firm = self._make_firm()
        pm.deactivate("counter", firm)  # not active — noop
        assert not pm.is_active("counter")

    def test_activate_all(self):
        pm = PluginManager()
        pm.register(CounterPlugin())
        pm.register(MinimalPlugin())
        firm = self._make_firm()
        activated = pm.activate_all(firm)
        assert set(activated) == {"counter", "minimal"}
        assert pm.is_active("counter")
        assert pm.is_active("minimal")

    def test_activate_all_skips_failures(self):
        pm = PluginManager()
        pm.register(CounterPlugin())
        pm.register(FailingPlugin())
        firm = self._make_firm()
        activated = pm.activate_all(firm)
        assert "counter" in activated
        assert "fail-plugin" not in activated

    def test_deactivate_all(self):
        pm = PluginManager()
        pm.register(CounterPlugin())
        pm.register(MinimalPlugin())
        firm = self._make_firm()
        pm.activate_all(firm)
        pm.deactivate_all(firm)
        assert pm.active == []


# ── Plugin stats ─────────────────────────────────────────────────────────────


class TestPluginManagerStats:
    """Statistics and properties."""

    def test_registered_property(self):
        pm = PluginManager()
        assert pm.registered == []
        pm.register(CounterPlugin())
        assert pm.registered == ["counter"]

    def test_active_property(self):
        from firm.runtime import Firm
        pm = PluginManager()
        pm.register(CounterPlugin())
        assert pm.active == []
        firm = Firm(name="stats-test")
        pm.activate("counter", firm)
        assert pm.active == ["counter"]

    def test_get_stats(self):
        from firm.runtime import Firm
        pm = PluginManager()
        pm.register(CounterPlugin())
        pm.register(MinimalPlugin())
        firm = Firm(name="stats-test")
        pm.activate("counter", firm)

        stats = pm.get_stats()
        assert stats["registered"] == 2
        assert stats["active"] == 1
        assert len(stats["plugins"]) == 2
        # Find counter in plugins list
        counter_info = next(p for p in stats["plugins"] if p["name"] == "counter")
        assert counter_info["active"] is True
        assert counter_info["version"] == "1.0.0"


# ── End-to-end: plugin with event bus ────────────────────────────────────────


class TestPluginEventIntegration:
    """Plugin receiving events through the FIRM event bus."""

    def test_plugin_receives_action_events(self):
        from firm.runtime import Firm
        firm = Firm(name="plugin-e2e")
        p = CounterPlugin()
        firm.plugins.register(p)
        firm.plugins.activate("counter", firm)

        agent = firm.add_agent("worker", authority=0.5)
        assert p.action_count == 0

        firm.record_action(agent.id, success=True, description="task 1")
        assert p.action_count == 1

        firm.record_action(agent.id, success=True, description="task 2")
        assert p.action_count == 2

    def test_deactivated_plugin_stops_receiving(self):
        from firm.runtime import Firm
        firm = Firm(name="plugin-e2e")
        p = CounterPlugin()
        firm.plugins.register(p)
        firm.plugins.activate("counter", firm)

        agent = firm.add_agent("worker", authority=0.5)
        firm.record_action(agent.id, success=True, description="task 1")
        assert p.action_count == 1

        firm.plugins.deactivate("counter", firm)
        firm.record_action(agent.id, success=True, description="task 2")
        assert p.action_count == 1  # no new events
