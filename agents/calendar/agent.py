"""
Calendar Agent — multi-account calendar management.
Supports Google Calendar and Apple iCloud CalDAV.
All write operations (create/update/delete) require user confirmation via Apollo.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

import anthropic

from agents.base import BaseAgent
from agents.calendar.providers.base import CalendarProvider
from agents.calendar.providers.google import GoogleCalendarProvider
from agents.calendar.providers.apple import AppleCalDAVProvider
from shared.models import AgentName, AgentRequest, AgentResponse, CalendarEvent
from shared.registry import get_calendar_providers, get_provider_credential
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

CALENDAR_MODEL = "claude-sonnet-4-6"


class CalendarAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.CALENDAR)
        self._providers: list[CalendarProvider] = []
        self._anthropic = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)
        self._load_providers()

    def _load_providers(self) -> None:
        """Load all configured calendar providers from registry."""
        for config in get_calendar_providers():
            provider_type = config.get("provider")
            account = config.get("account", "")
            label = config.get("label", account)
            creds_env = config.get("credentials_env", "")

            try:
                if provider_type == "google":
                    self._providers.append(
                        GoogleCalendarProvider(
                            token_env=creds_env,
                            account=account,
                            label=label,
                        )
                    )
                    logger.info(f"Loaded Google Calendar: {label}")

                elif provider_type == "apple_caldav":
                    secrets = get_secrets()
                    self._providers.append(
                        AppleCalDAVProvider(
                            url=secrets.apple_caldav_url,
                            username=secrets.apple_caldav_user or account,
                            password=secrets.apple_caldav_token or "",
                            account=account,
                            label=label,
                        )
                    )
                    logger.info(f"Loaded Apple CalDAV: {label}")

            except Exception as e:
                logger.error(f"Failed to load calendar provider {provider_type}: {e}")

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task.lower()
        context = request.context

        if any(k in task for k in ["list", "show", "what", "today", "tomorrow", "schedule", "upcoming", "find", "search", "when", "next", "appointment", "meeting", "event"]):
            return await self._handle_list_events(request)

        if any(k in task for k in ["create", "add", "schedule", "book", "set up"]):
            return await self._handle_create_event(request)

        if any(k in task for k in ["update", "change", "reschedule", "move", "modify"]):
            return await self._handle_update_event(request)

        if any(k in task for k in ["delete", "cancel", "remove"]):
            return await self._handle_delete_event(request)

        if any(k in task for k in ["briefing", "summary", "morning", "day"]):
            return await self._handle_daily_briefing(request)

        return await self._handle_general(request)

    async def _handle_list_events(self, request: AgentRequest) -> AgentResponse:
        """List events across all providers."""
        context = request.context
        now = datetime.utcnow()

        # Determine time range from context or natural language
        start = _parse_datetime(context.get("start")) or now
        end = _parse_datetime(context.get("end")) or (now + timedelta(days=90))

        if not self._providers:
            return self._error(request, "No calendar providers configured.")

        all_events: list[CalendarEvent] = []
        errors: list[str] = []

        for provider in self._providers:
            try:
                events = await provider.list_events(start, end)
                all_events.extend(events)
            except Exception as e:
                logger.error(f"Error listing events from {provider.account_label}: {e}")
                errors.append(f"{provider.account_label}: {e}")

        all_events.sort(key=lambda e: e.start)

        if not all_events and not errors:
            return self._ok(request, result="No events found in the specified time range.")

        lines = [f"📅 *Calendar* ({start.strftime('%b %d')} – {end.strftime('%b %d')})\n"]
        for event in all_events[:20]:
            time_str = event.start.strftime("%a %b %d, %I:%M %p")
            lines.append(
                f"• `{time_str}` — **{event.title}**"
                + (f" @ {event.location}" if event.location else "")
                + f" _{event.account}_"
            )

        if errors:
            lines.append(f"\n⚠️ Errors: {', '.join(errors)}")

        return self._ok(
            request,
            result="\n".join(lines),
            data={"event_count": len(all_events)},
        )

    async def _handle_create_event(self, request: AgentRequest) -> AgentResponse:
        """Create a calendar event — REQUIRES CONFIRMATION."""
        context = request.context

        # Parse event details from context or ask Claude to extract them
        event = await self._extract_event_details(request.task, context)

        if not event:
            return self._error(
                request,
                "Could not parse event details. Please specify title, date, time, and duration."
            )

        # Require confirmation before creating
        confirmation_id = str(uuid.uuid4())
        description = (
            f"Create calendar event:\n"
            f"📋 {event.title}\n"
            f"🕐 {event.start.strftime('%A, %B %d at %I:%M %p')} – "
            f"{event.end.strftime('%I:%M %p')}"
            + (f"\n📍 {event.location}" if event.location else "")
        )

        return self._needs_confirmation(
            request,
            description=description,
            action_payload={"action": "create_event", "event": event.model_dump(mode="json")},
            confirmation_id=confirmation_id,
        )

    async def execute_confirmed_create(
        self, event_data: dict[str, Any]
    ) -> CalendarEvent:
        """Execute event creation after confirmation."""
        event = CalendarEvent(**event_data)
        if not self._providers:
            raise RuntimeError("No calendar providers available")
        # Create in first available provider by default
        return await self._providers[0].create_event(event)

    async def _handle_update_event(self, request: AgentRequest) -> AgentResponse:
        return self._error(
            request,
            "Event updates require finding the specific event first. "
            "Please list your events and specify which one to modify."
        )

    async def _handle_delete_event(self, request: AgentRequest) -> AgentResponse:
        return self._error(
            request,
            "Event deletion requires finding the specific event first. "
            "Please list your events and specify which one to delete."
        )

    async def _handle_daily_briefing(self, request: AgentRequest) -> AgentResponse:
        """Generate a morning briefing of today's schedule."""
        now = datetime.utcnow()
        start = now.replace(hour=0, minute=0, second=0)
        end = now.replace(hour=23, minute=59, second=59)

        all_events: list[CalendarEvent] = []
        for provider in self._providers:
            try:
                events = await provider.list_events(start, end)
                all_events.extend(events)
            except Exception as e:
                logger.error(f"Briefing error from {provider.account_label}: {e}")

        all_events.sort(key=lambda e: e.start)

        if not all_events:
            return self._ok(
                request,
                result=f"📅 No events scheduled for today ({now.strftime('%A, %B %d')})."
            )

        lines = [f"📅 *Today's Schedule — {now.strftime('%A, %B %d')}*\n"]
        for event in all_events:
            time_str = event.start.strftime("%I:%M %p")
            end_str = event.end.strftime("%I:%M %p")
            lines.append(
                f"• {time_str}–{end_str} **{event.title}**"
                + (f" @ {event.location}" if event.location else "")
            )

        return self._ok(
            request,
            result="\n".join(lines),
            data={"event_count": len(all_events)},
        )

    async def _handle_general(self, request: AgentRequest) -> AgentResponse:
        """Use Claude to handle general calendar queries."""
        response = self._anthropic.messages.create(
            model=CALENDAR_MODEL,
            max_tokens=1024,
            system="You are a calendar assistant. Answer concisely. Format for Telegram Markdown.",
            messages=[{"role": "user", "content": request.task}],
        )
        return self._ok(request, result=response.content[0].text)

    async def _extract_event_details(
        self, task: str, context: dict[str, Any]
    ) -> CalendarEvent | None:
        """Use Claude to extract structured event details from natural language."""
        prompt = (
            f"Extract calendar event details from this request:\n{task}\n"
            f"Additional context: {context}\n"
            f"Today's date/time: {datetime.utcnow().isoformat()}\n\n"
            "Return JSON with fields: title, start (ISO format), end (ISO format), "
            "location (optional), description (optional). "
            "Infer reasonable defaults (1-hour duration if not specified). "
            "Return ONLY valid JSON, no explanation."
        )

        try:
            response = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            text = response.content[0].text.strip()
            # Strip markdown code blocks if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return CalendarEvent(
                provider="google",
                account="",
                title=data["title"],
                start=datetime.fromisoformat(data["start"]),
                end=datetime.fromisoformat(data["end"]),
                location=data.get("location"),
                description=data.get("description"),
            )
        except Exception as e:
            logger.error(f"Failed to extract event details: {e}")
            return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


# FastAPI app entry point
_agent = CalendarAgent()
app = _agent.app
