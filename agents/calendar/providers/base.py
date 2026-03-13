"""
CalendarProvider interface — all calendar providers implement this.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from shared.models import CalendarEvent


class CalendarProvider(ABC):
    """Abstract calendar provider. Google, Apple, and Outlook all implement this."""

    @abstractmethod
    async def list_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        """List events in the given time range."""
        ...

    @abstractmethod
    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        """Create a new event. Returns the created event with its ID."""
        ...

    @abstractmethod
    async def update_event(
        self, event_id: str, event: CalendarEvent
    ) -> CalendarEvent:
        """Update an existing event."""
        ...

    @abstractmethod
    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> None:
        """Delete an event by ID."""
        ...

    @abstractmethod
    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Optional[CalendarEvent]:
        """Get a single event by ID."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier string, e.g. 'google', 'apple_caldav'."""
        ...

    @property
    @abstractmethod
    def account_label(self) -> str:
        """Human-readable account label, e.g. 'Work Calendar'."""
        ...
