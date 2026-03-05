"""
firm.core.events — Event Bus (Pub/Sub Observer Pattern)

Cross-layer communication via typed events. Any subsystem can emit
events, and any observer can subscribe to event types.

Usage:
    bus = EventBus()
    bus.subscribe("authority.changed", my_handler)
    bus.emit("authority.changed", {"agent_id": "a1", "delta": 0.05})

Design:
    - Synchronous dispatch (no async/threading)
    - Handlers are called in subscription order
    - Exceptions in handlers are caught and logged, never propagated
    - Wildcard subscriptions via "*" suffix: "authority.*" matches all authority events
    - Event history retained for replay/audit
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    """An immutable event emitted on the event bus."""

    type: str
    data: dict[str, Any]
    source: str = ""  # e.g. "authority_engine", "governance", "runtime"
    timestamp: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return f"Event(type={self.type!r}, source={self.source!r})"


class EventBus:
    """
    Publish/subscribe event bus for intra-FIRM communication.

    Supports:
        - Exact subscriptions: "authority.changed"
        - Wildcard subscriptions: "authority.*"
        - Global subscriptions: "*"
        - Event history for replay
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._max_history = max_history

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        Subscribe a handler to an event type.

        Args:
            event_type: Exact type or wildcard pattern (e.g. "authority.*" or "*")
            handler: Callable that accepts an Event
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Remove a handler. Returns True if found."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    def emit(self, event_type: str, data: dict[str, Any] | None = None,
             source: str = "") -> Event:
        """
        Emit an event, dispatching to all matching handlers.

        Matching rules:
            1. Exact match on event_type
            2. Wildcard: "prefix.*" matches "prefix.anything"
            3. Global: "*" matches everything
        """
        event = Event(type=event_type, data=data or {}, source=source)
        self._history.append(event)

        # Trim history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Collect matching handlers
        matched: list[EventHandler] = []

        # Exact match
        matched.extend(self._handlers.get(event_type, []))

        # Wildcard matches
        for pattern, handlers in self._handlers.items():
            if pattern == event_type:
                continue  # already added
            if pattern == "*":
                matched.extend(handlers)
            elif pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event_type.startswith(prefix + "."):
                    matched.extend(handlers)

        # Dispatch
        for handler in matched:
            try:
                handler(event)
            except Exception as exc:
                logger.error(
                    "Event handler %s failed on %s: %s",
                    handler.__name__ if hasattr(handler, "__name__") else handler,
                    event_type,
                    exc,
                )

        return event

    def get_history(
        self,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[Event]:
        """Get recent events, optionally filtered by type."""
        if event_type is None:
            return list(self._history[-limit:])
        return [e for e in self._history if e.type == event_type][-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers."""
        return sum(len(h) for h in self._handlers.values())

    @property
    def event_count(self) -> int:
        """Total events in history."""
        return len(self._history)

    def get_stats(self) -> dict[str, Any]:
        """Get event bus statistics."""
        type_counts: dict[str, int] = {}
        for event in self._history:
            type_counts[event.type] = type_counts.get(event.type, 0) + 1
        return {
            "total_events": len(self._history),
            "handler_count": self.handler_count,
            "subscription_types": list(self._handlers.keys()),
            "event_type_counts": type_counts,
        }
