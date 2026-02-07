"""Lifecycle callback base classes for AuraGrid Python MAS applications.

Mirrors the C# ``LifecyclePhase``, ``LifecycleContext``, and
``ILifecycleCallback`` from ``AuraGrid.Abstractions.Lifecycle``.

Usage::

    from auragrid.lifecycle import LifecycleCallback, LifecycleContext, LifecyclePhase

    class MyInstaller(LifecycleCallback):
        async def execute(self, context: LifecycleContext) -> None:
            if context.phase == LifecyclePhase.INSTALL:
                print(f"Installing {context.app_id} v{context.app_version}")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LifecyclePhase(Enum):
    """Lifecycle phases matching C# ``LifecyclePhase`` enum."""

    INSTALL = "Install"
    STARTUP = "Startup"
    SHUTDOWN = "Shutdown"
    UNINSTALL = "Uninstall"


@dataclass(frozen=True)
class LifecycleContext:
    """Context provided to lifecycle callbacks.

    Mirrors C# ``LifecycleContext`` from ``AuraGrid.Abstractions.Lifecycle``.
    """

    app_id: str
    node_id: str
    phase: LifecyclePhase
    app_version: str
    previous_version: Optional[str] = None
    environment: dict[str, str] = field(default_factory=dict)


class LifecycleCallback(ABC):
    """Abstract base class for lifecycle callbacks.

    Subclass and implement ``execute`` to handle lifecycle events.
    """

    @abstractmethod
    async def execute(self, context: LifecycleContext) -> None:
        """Execute the lifecycle callback.

        Args:
            context: The lifecycle context with app info and phase.
        """
        ...
