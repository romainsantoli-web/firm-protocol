"""
Tests for firm.core.events — Event Bus (pub/sub observer pattern)
"""

import time
from unittest.mock import MagicMock

import pytest

from firm.core.events import Event, EventBus


# ── Event dataclass ──────────────────────────────────────────────────────────


class TestEvent:
    """Tests for the Event frozen dataclass."""

    def test_create_event(self):
        e = Event(type="test.event", data={"key": "value"}, source="unit-test")
        assert e.type == "test.event"
        assert e.data == {"key": "value"}
        assert e.source == "unit-test"
        assert isinstance(e.timestamp, float)

    def test_event_immutable(self):
        e = Event(type="test", data={})
        with pytest.raises(AttributeError):
            e.type = "changed"

    def test_event_defaults(self):
        e = Event(type="t", data={})
        assert e.source == ""
        assert e.timestamp <= time.time()

    def test_event_repr(self):
        e = Event(type="a.b", data={}, source="src")
        assert "a.b" in repr(e)
        assert "src" in repr(e)


# ── EventBus basics ─────────────────────────────────────────────────────────


class TestEventBusBasics:
    """Core subscribe/emit/unsubscribe."""

    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []
        bus.subscribe("test", lambda e: received.append(e))
        event = bus.emit("test", {"v": 1})
        assert len(received) == 1
        assert received[0] is event
        assert event.type == "test"

    def test_emit_returns_event(self):
        bus = EventBus()
        e = bus.emit("foo", {"a": 1}, source="bar")
        assert isinstance(e, Event)
        assert e.type == "foo"
        assert e.source == "bar"

    def test_emit_no_data(self):
        bus = EventBus()
        e = bus.emit("empty")
        assert e.data == {}

    def test_multiple_subscribers(self):
        bus = EventBus()
        calls = []
        bus.subscribe("x", lambda e: calls.append("h1"))
        bus.subscribe("x", lambda e: calls.append("h2"))
        bus.emit("x")
        assert calls == ["h1", "h2"]

    def test_unsubscribe(self):
        bus = EventBus()
        calls = []
        handler = lambda e: calls.append(1)  # noqa: E731
        bus.subscribe("x", handler)
        bus.emit("x")
        assert len(calls) == 1

        assert bus.unsubscribe("x", handler) is True
        bus.emit("x")
        assert len(calls) == 1  # no more calls

    def test_unsubscribe_not_found(self):
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        assert bus.unsubscribe("nonexistent", handler) is False

    def test_no_duplicate_subscription(self):
        bus = EventBus()
        calls = []
        handler = lambda e: calls.append(1)  # noqa: E731
        bus.subscribe("x", handler)
        bus.subscribe("x", handler)  # duplicate
        bus.emit("x")
        assert len(calls) == 1  # only once

    def test_emit_no_subscribers(self):
        """Emitting to an event with no subscribers shouldn't crash."""
        bus = EventBus()
        e = bus.emit("nobody.listens", {"data": True})
        assert e.type == "nobody.listens"


# ── Wildcard matching ────────────────────────────────────────────────────────


class TestEventBusWildcards:
    """Wildcard and global subscriptions."""

    def test_wildcard_prefix(self):
        bus = EventBus()
        received = []
        bus.subscribe("authority.*", lambda e: received.append(e.type))
        bus.emit("authority.changed")
        bus.emit("authority.reset")
        bus.emit("governance.vote")  # should NOT match
        assert received == ["authority.changed", "authority.reset"]

    def test_global_wildcard(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda e: received.append(e.type))
        bus.emit("a")
        bus.emit("b.c")
        bus.emit("x.y.z")
        assert len(received) == 3

    def test_wildcard_no_partial_match(self):
        """'auth.*' should NOT match 'authentication.changed'."""
        bus = EventBus()
        received = []
        bus.subscribe("auth.*", lambda e: received.append(1))
        bus.emit("authentication.changed")
        assert len(received) == 0

    def test_exact_and_wildcard_combined(self):
        """Both exact and wildcard handlers fire."""
        bus = EventBus()
        exact = []
        wild = []
        bus.subscribe("a.b", lambda e: exact.append(1))
        bus.subscribe("a.*", lambda e: wild.append(1))
        bus.emit("a.b")
        assert len(exact) == 1
        assert len(wild) == 1

    def test_wildcard_does_not_match_exact_prefix(self):
        """'a.*' should NOT match 'a' (no dot separator)."""
        bus = EventBus()
        received = []
        bus.subscribe("a.*", lambda e: received.append(1))
        bus.emit("a")
        assert len(received) == 0


# ── Exception safety ─────────────────────────────────────────────────────────


class TestEventBusExceptionSafety:
    """Handlers that throw should not break other handlers."""

    def test_handler_exception_caught(self):
        bus = EventBus()
        calls = []

        def bad_handler(e):
            raise RuntimeError("boom")

        def good_handler(e):
            calls.append(1)

        bus.subscribe("x", bad_handler)
        bus.subscribe("x", good_handler)
        bus.emit("x")  # should not raise
        assert len(calls) == 1

    def test_handler_exception_logged(self, caplog):
        bus = EventBus()

        def fail(e):
            raise ValueError("oops")

        bus.subscribe("err", fail)
        import logging
        with caplog.at_level(logging.ERROR, logger="firm.core.events"):
            bus.emit("err")
        assert "failed" in caplog.text.lower() or "oops" in caplog.text


# ── History ──────────────────────────────────────────────────────────────────


class TestEventBusHistory:
    """Event history and replay."""

    def test_history_stored(self):
        bus = EventBus()
        bus.emit("a")
        bus.emit("b")
        bus.emit("c")
        history = bus.get_history()
        assert len(history) == 3
        assert [e.type for e in history] == ["a", "b", "c"]

    def test_history_filtered_by_type(self):
        bus = EventBus()
        bus.emit("a")
        bus.emit("b")
        bus.emit("a")
        history = bus.get_history(event_type="a")
        assert len(history) == 2
        assert all(e.type == "a" for e in history)

    def test_history_limit(self):
        bus = EventBus()
        for i in range(10):
            bus.emit(f"e{i}")
        history = bus.get_history(limit=3)
        assert len(history) == 3
        assert history[0].type == "e7"

    def test_history_max_cap(self):
        bus = EventBus(max_history=5)
        for i in range(10):
            bus.emit(f"e{i}")
        assert bus.event_count == 5
        history = bus.get_history()
        assert history[0].type == "e5"

    def test_clear_history(self):
        bus = EventBus()
        bus.emit("a")
        bus.emit("b")
        bus.clear_history()
        assert bus.event_count == 0
        assert bus.get_history() == []


# ── Stats & properties ───────────────────────────────────────────────────────


class TestEventBusStats:
    """handler_count, event_count, get_stats."""

    def test_handler_count(self):
        bus = EventBus()
        assert bus.handler_count == 0
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.subscribe("b", lambda e: None)
        assert bus.handler_count == 3

    def test_event_count(self):
        bus = EventBus()
        assert bus.event_count == 0
        bus.emit("x")
        bus.emit("y")
        assert bus.event_count == 2

    def test_get_stats(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.emit("a")
        bus.emit("a")
        bus.emit("b")
        stats = bus.get_stats()
        assert stats["total_events"] == 3
        assert stats["handler_count"] == 1
        assert "a" in stats["subscription_types"]
        assert stats["event_type_counts"]["a"] == 2
        assert stats["event_type_counts"]["b"] == 1


# ── Integration with Firm ────────────────────────────────────────────────────


class TestEventBusFirmIntegration:
    """Events emitted by the FIRM runtime."""

    def test_firm_created_event(self):
        from firm.runtime import Firm
        firm = Firm(name="evt-test")
        history = firm.events.get_history("firm.created")
        assert len(history) == 1
        assert history[0].data["name"] == "evt-test"
        assert history[0].source == "runtime"

    def test_agent_added_event(self):
        from firm.runtime import Firm
        firm = Firm(name="evt-test")
        received = []
        firm.events.subscribe("agent.added", lambda e: received.append(e))
        agent = firm.add_agent("worker", authority=0.6)
        assert len(received) == 1
        assert received[0].data["name"] == "worker"
        assert received[0].data["authority"] == 0.6

    def test_action_recorded_event(self):
        from firm.runtime import Firm
        firm = Firm(name="evt-test")
        agent = firm.add_agent("w", authority=0.5)
        received = []
        firm.events.subscribe("action.recorded", lambda e: received.append(e))
        firm.record_action(agent.id, success=True, description="test task")
        assert len(received) == 1
        assert received[0].data["agent_id"] == agent.id
        assert received[0].data["success"] is True

    def test_wildcard_captures_firm_events(self):
        from firm.runtime import Firm
        firm = Firm(name="evt-test")
        all_events = []
        firm.events.subscribe("*", lambda e: all_events.append(e.type))
        firm.add_agent("a", authority=0.5)
        firm.record_action(firm.get_agents()[0].id, True, "x")
        # Should capture agent.added + action.recorded (firm.created happened before subscribe)
        assert "agent.added" in all_events
        assert "action.recorded" in all_events
