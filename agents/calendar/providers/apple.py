"""
Apple iCloud Calendar provider via CalDAV.
Uses an app-specific password (not the main Apple ID password).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from shared.models import CalendarEvent
from .base import CalendarProvider

logger = logging.getLogger(__name__)

try:
    import caldav
    from caldav.elements import dav, cdav
    CALDAV_AVAILABLE = True
except ImportError:
    CALDAV_AVAILABLE = False
    logger.warning("caldav not installed — Apple CalDAV unavailable")


class AppleCalDAVProvider(CalendarProvider):
    """Apple iCloud calendar via CalDAV protocol."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        account: str,
        label: str,
    ) -> None:
        self._url = url
        self._username = username
        self._password = password
        self._account = account
        self._label = label
        self._client = None
        self._principal = None

    @property
    def provider_name(self) -> str:
        return "apple_caldav"

    @property
    def account_label(self) -> str:
        return self._label

    def _get_client(self):
        if not CALDAV_AVAILABLE:
            raise RuntimeError("caldav not installed. Run: pip install caldav")
        if self._client is None:
            self._client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
            )
            self._principal = self._client.principal()
        return self._client

    def _get_calendars(self) -> list:
        self._get_client()
        return self._principal.calendars()

    async def list_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        calendars = self._get_calendars()
        events = []

        for cal in calendars:
            try:
                cal_events = cal.date_search(start=start, end=end, expand=True)
                for e in cal_events:
                    parsed = self._to_calendar_event(e, cal.name)
                    if parsed:
                        events.append(parsed)
            except Exception as ex:
                logger.error(f"CalDAV list_events error for calendar '{cal.name}': {ex}")

        return sorted(events, key=lambda e: e.start)

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        calendars = self._get_calendars()
        # Use first available calendar (or search by name if specified)
        target_cal = calendars[0] if calendars else None
        if not target_cal:
            raise RuntimeError("No CalDAV calendars available")

        ical = self._to_ical(event)
        created = target_cal.save_event(ical)

        # Parse and return the created event
        parsed = self._to_calendar_event(created, target_cal.name)
        return parsed or event

    async def update_event(self, event_id: str, event: CalendarEvent) -> CalendarEvent:
        raise NotImplementedError("CalDAV event update not yet implemented")

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> None:
        raise NotImplementedError("CalDAV event deletion not yet implemented")

    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Optional[CalendarEvent]:
        raise NotImplementedError("CalDAV get_event not yet implemented")

    def _to_calendar_event(
        self, caldav_event, calendar_name: str
    ) -> Optional[CalendarEvent]:
        """Convert caldav event to CalendarEvent."""
        try:
            from icalendar import Calendar as iCal
            cal = iCal.from_ical(caldav_event.data)
            for component in cal.walk():
                if component.name == "VEVENT":
                    dtstart = component.get("DTSTART")
                    dtend = component.get("DTEND")

                    start = dtstart.dt if dtstart else datetime.utcnow()
                    end = dtend.dt if dtend else start + timedelta(hours=1)

                    # Convert date to datetime if needed
                    if hasattr(start, "date") and not hasattr(start, "hour"):
                        start = datetime.combine(start, datetime.min.time())
                    if hasattr(end, "date") and not hasattr(end, "hour"):
                        end = datetime.combine(end, datetime.min.time())

                    return CalendarEvent(
                        event_id=str(component.get("UID", "")),
                        provider=self.provider_name,
                        account=self._account,
                        title=str(component.get("SUMMARY", "(No title)")),
                        start=start.replace(tzinfo=None) if hasattr(start, "tzinfo") else start,
                        end=end.replace(tzinfo=None) if hasattr(end, "tzinfo") else end,
                        location=str(component.get("LOCATION", "") or ""),
                        description=str(component.get("DESCRIPTION", "") or ""),
                    )
        except Exception as e:
            logger.error(f"Error parsing CalDAV event: {e}")
        return None

    def _to_ical(self, event: CalendarEvent) -> str:
        """Convert CalendarEvent to iCal format string."""
        import uuid
        uid = event.event_id or str(uuid.uuid4())
        start_str = event.start.strftime("%Y%m%dT%H%M%SZ")
        end_str = event.end.strftime("%Y%m%dT%H%M%SZ")

        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Apollo//Apollo Assistant//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTART:{start_str}\r\n"
            f"DTEND:{end_str}\r\n"
            f"SUMMARY:{event.title}\r\n"
            + (f"LOCATION:{event.location}\r\n" if event.location else "")
            + (f"DESCRIPTION:{event.description}\r\n" if event.description else "")
            + "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
