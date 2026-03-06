"""
firm.core.plugins — Plugin / Extension System

Allows third-party or custom code to hook into FIRM lifecycle events
without modifying core modules. Plugins register via a simple interface
and receive events through the event bus.

Usage:
    class MetricsPlugin(FirmPlugin):
        name = "metrics"
        version = "1.0.0"

        def on_activate(self, firm):
            self.action_count = 0
            firm.events.subscribe("action.recorded", self._on_action)

        def _on_action(self, event):
            self.action_count += 1

    firm = Firm(name="my-firm")
    firm.plugins.register(MetricsPlugin())
    firm.plugins.activate_all(firm)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from firm.runtime import Firm

logger = logging.getLogger(__name__)


class FirmPlugin(ABC):
    """
    Base class for FIRM plugins.

    Subclasses must define `name` and `version` and implement
    `on_activate` and `on_deactivate`.
    """

    name: str = "unnamed"
    version: str = "0.0.0"
    description: str = ""

    @abstractmethod
    def on_activate(self, firm: "Firm") -> None:
        """Called when the plugin is activated. Subscribe to events here."""
        ...

    def on_deactivate(self, firm: "Firm") -> None:
        """Called when the plugin is deactivated. Cleanup resources."""
        pass

    def get_info(self) -> dict[str, str]:
        """Return plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }


class PluginManager:
    """
    Manages plugin lifecycle: register, activate, deactivate, query.

    Plugins are registered first, then activated (which connects them
    to the FIRM's event bus and runtime).
    """

    def __init__(self) -> None:
        self._plugins: dict[str, FirmPlugin] = {}
        self._active: set[str] = set()

    def register(self, plugin: FirmPlugin) -> None:
        """Register a plugin. Raises ValueError if name already taken."""
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")
        self._plugins[plugin.name] = plugin
        logger.info("Plugin '%s' v%s registered", plugin.name, plugin.version)

    def unregister(self, name: str) -> bool:
        """Unregister a plugin (deactivates first if active). Returns True if found."""
        if name not in self._plugins:
            return False
        if name in self._active:
            # Can't deactivate without firm ref — just mark inactive
            self._active.discard(name)
        del self._plugins[name]
        return True

    def activate(self, name: str, firm: "Firm") -> None:
        """Activate a specific plugin."""
        plugin = self._plugins.get(name)
        if plugin is None:
            raise KeyError(f"Plugin '{name}' not registered")
        if name in self._active:
            return  # Already active
        try:
            plugin.on_activate(firm)
            self._active.add(name)
            logger.info("Plugin '%s' activated", name)
        except Exception as exc:
            logger.error("Plugin '%s' failed to activate: %s", name, exc)
            raise

    def deactivate(self, name: str, firm: "Firm") -> None:
        """Deactivate a specific plugin."""
        plugin = self._plugins.get(name)
        if plugin is None:
            raise KeyError(f"Plugin '{name}' not registered")
        if name not in self._active:
            return
        try:
            plugin.on_deactivate(firm)
        except Exception as exc:
            logger.error("Plugin '%s' deactivation error: %s", name, exc)
        self._active.discard(name)

    def activate_all(self, firm: "Firm") -> list[str]:
        """Activate all registered plugins. Returns list of activated names."""
        activated = []
        for name in list(self._plugins.keys()):
            if name not in self._active:
                try:
                    self.activate(name, firm)
                    activated.append(name)
                except Exception:
                    pass  # Logged in activate()
        return activated

    def deactivate_all(self, firm: "Firm") -> None:
        """Deactivate all active plugins."""
        for name in list(self._active):
            self.deactivate(name, firm)

    def get_plugin(self, name: str) -> FirmPlugin | None:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def is_active(self, name: str) -> bool:
        """Check if a plugin is active."""
        return name in self._active

    @property
    def registered(self) -> list[str]:
        """List registered plugin names."""
        return list(self._plugins.keys())

    @property
    def active(self) -> list[str]:
        """List active plugin names."""
        return list(self._active)

    def get_stats(self) -> dict[str, Any]:
        """Get plugin manager statistics."""
        return {
            "registered": len(self._plugins),
            "active": len(self._active),
            "plugins": [
                {
                    **p.get_info(),
                    "active": p.name in self._active,
                }
                for p in self._plugins.values()
            ],
        }
