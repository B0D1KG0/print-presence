from __future__ import annotations

from abc import ABC, abstractmethod

from ..status import PrinterStatus


class Printer(ABC):
    """A printer backend. Runs its own connection in the background."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def start(self) -> None:
        """Start connecting (non-blocking). Must reconnect by itself on failures."""

    @abstractmethod
    def stop(self) -> None:
        """Disconnect and release resources."""

    @abstractmethod
    def status(self) -> PrinterStatus:
        """Return the latest known status (thread-safe snapshot)."""
