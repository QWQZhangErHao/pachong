"""Lightweight dependency injection container.

All major components (queue client, DB pools, network sessions) are registered
at startup and resolved by name. This avoids passing a dozen dependencies
through every function signature while keeping testability.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_registry: dict[str, Any] = {}
_factories: dict[str, Callable[[], Any]] = {}


def register(name: str, instance: Any) -> None:
    """Register a singleton instance."""
    _registry[name] = instance


def register_factory(name: str, factory: Callable[[], Any]) -> None:
    """Register a lazy factory — called on first resolve()."""
    _factories[name] = factory


def resolve(name: str) -> Any:
    """Resolve a component by name. Lazily instantiates factories on first call."""
    if name in _registry:
        return _registry[name]
    if name in _factories:
        instance = _factories[name]()
        _registry[name] = instance
        return instance
    raise KeyError(f"Component '{name}' not registered. Available: {list(_registry)} | {list(_factories)}")


def unregister(name: str) -> None:
    """Remove a component (useful for testing)."""
    _registry.pop(name, None)
    _factories.pop(name, None)


def clear() -> None:
    """Reset all registrations (test cleanup)."""
    _registry.clear()
    _factories.clear()
