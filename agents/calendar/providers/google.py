"""
Google Calendar provider via Google Calendar API v3.
Uses OAuth2 credentials stored in env or a token file.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from shared.models import CalendarEvent
from .base import CalendarProvider

logger = logging.getLogger(__name__)

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    logger.warning("google-api-python-client not installed — Google Calendar unavailable")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar via Google API."""

    def __init__(self, token_env: str, account: str, label: str) -> None:
        self._token_env = token_env
        self._account = account
        self._label = label
        self._service = None

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def account_label(self) -> str:
        return self._label

    def _get_service(self):
        """Build and cache the Google Calendar service."""
        if self._service:
            return self._service

        if not GOOGLE_AVAILABLE:
            raise RuntimeError("google-api-python-client not installed")

        token_data = os.environ.get(self._token_env)
        if not token_data:
            raise RuntimeError(f"Google Calendar token not found in env: {self._token_env}")

        try:
            creds_dict = json.loads(token_data)
        except json.JSONDecodeError:
            # Maybe it's a file path
            if os.path.exists(token_data):
                with open(token_data) as f:
                    creds_dict = json.load(f)
            else:
                raise RuntimeError(f"Cannot parse Google Calendar token from {self._token_env}")

        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    async def list_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        service = self._get_service()
        try:
            result = service.events().list(
                calendarId=calendar_id,
                timeMin=start.isoformat() + "Z",
                timeMax=end.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            ).execute()

            events = result.get("items", [])
            return [self._to_calendar_event(e) for e in events]
        except HttpError as e:
            logger.error(f"Google Calendar list_events error: {e}")
            raise

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        service = self._get_service()
        body = self._from_calendar_event(event)
        try:
            created = service.events().insert(
                calendarId="primary", body=body
            ).execute()
            return self._to_calendar_event(created)
        except HttpError as e:
            logger.error(f"Google Calendar create_event error: {e}")
            raise

    async def update_event(self, event_id: str, event: CalendarEvent) -> CalendarEvent:
        service = self._get_service()
        body = self._from_calendar_event(event)
        try:
            updated = service.events().update(
                calendarId="primary", eventId=event_id, body=body
            ).execute()
            return self._to_calendar_event(updated)
        except HttpError as e:
            logger.error(f"Google Calendar update_event error: {e}")
            raise

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> None:
        service = self._get_service()
        try:
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        except HttpError as e:
            logger.error(f"Google Calendar delete_event error: {e}")
            raise

    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Optional[CalendarEvent]:
        service = self._get_service()
        try:
            event = service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return self._to_calendar_event(event)
        except HttpError as e:
            if e.resp.status == 404:
                return None
            raise

    def _to_calendar_event(self, g_event: dict) -> CalendarEvent:
        """Convert Google Calendar event dict to CalendarEvent."""
        start_raw = g_event.get("start", {})
        end_raw = g_event.get("end", {})

        start = _parse_google_dt(start_raw)
        end = _parse_google_dt(end_raw)

        return CalendarEvent(
            event_id=g_event.get("id"),
            provider=self.provider_name,
            account=self._account,
            title=g_event.get("summary", "(No title)"),
            start=start,
            end=end,
            location=g_event.get("location"),
            description=g_event.get("description"),
            attendees=[
                a.get("email", "") for a in g_event.get("attendees", [])
            ],
            url=g_event.get("htmlLink"),
        )

    def _from_calendar_event(self, event: CalendarEvent) -> dict:
        """Convert CalendarEvent to Google Calendar API format."""
        return {
            "summary": event.title,
            "location": event.location,
            "description": event.description,
            "start": {
                "dateTime": event.start.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": event.end.isoformat(),
                "timeZone": "UTC",
            },
            "attendees": [{"email": e} for e in event.attendees],
        }


def _parse_google_dt(dt_dict: dict) -> datetime:
    """Parse Google Calendar dateTime or date to a datetime."""
    if "dateTime" in dt_dict:
        dt_str = dt_dict["dateTime"]
        # Remove Z suffix and parse
        dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str).replace(tzinfo=None)
    elif "date" in dt_dict:
        return datetime.strptime(dt_dict["date"], "%Y-%m-%d")
    return datetime.utcnow()
