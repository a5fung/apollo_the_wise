"""
Travel Agent — flight/hotel research, trip planning, credit card perks optimization.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import anthropic

from agents.base import BaseAgent
from agents.travel.card_perks import (
    AMEX_PLATINUM,
    format_trip_perks,
    get_lounge_access,
    recommend_card_for_booking,
)
from shared.models import AgentName, AgentRequest, AgentResponse
from shared.registry import get_credit_cards
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

TRAVEL_MODEL = "claude-sonnet-4-6"


class TravelAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.TRAVEL)
        self._anthropic = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task.lower()
        context = request.context

        if any(k in task for k in ["flight", "fly", "airfare", "airline"]):
            return await self._handle_flight_research(request)

        if any(k in task for k in ["hotel", "stay", "accommodation", "resort"]):
            return await self._handle_hotel_research(request)

        if any(k in task for k in ["itinerary", "trip", "plan", "travel to"]):
            return await self._handle_trip_planning(request)

        if any(k in task for k in ["lounge", "airport lounge", "centurion"]):
            return await self._handle_lounge_lookup(request)

        if any(k in task for k in ["perks", "benefits", "card", "amex", "points", "credit"]):
            return await self._handle_perks_query(request)

        return await self._handle_general_travel(request)

    async def _handle_flight_research(self, request: AgentRequest) -> AgentResponse:
        """Research flights using Claude + browser automation."""
        context = request.context
        origin = context.get("origin", "")
        destination = context.get("destination", "")
        date_str = context.get("date", "")

        # Use Claude to research flights (would use browser in full implementation)
        prompt = (
            f"Research flights for this request: {request.task}\n"
            f"Origin: {origin}, Destination: {destination}, Date: {date_str}\n\n"
            "Provide practical advice about:\n"
            "1. Best airlines/routes for this route\n"
            "2. Typical price ranges\n"
            "3. Best booking timing\n"
            "4. Amex Platinum benefits: book directly or via amextravel.com for 5x points\n"
            "5. Relevant credit card perks (lounge access, insurance coverage)\n\n"
            "Note: For real-time prices, use Google Flights or Kayak. "
            "Format for Telegram Markdown."
        )

        response = self._anthropic.messages.create(
            model=TRAVEL_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        result = response.content[0].text

        # Append card perks if we have origin/destination
        if origin and destination:
            perks = format_trip_perks(
                origin=origin.upper()[:3],
                destination=destination.upper()[:3],
            )
            result = f"{result}\n\n{perks}"

        return self._ok(request, result=result)

    async def _handle_hotel_research(self, request: AgentRequest) -> AgentResponse:
        """Research hotels with FHR awareness."""
        context = request.context
        destination = context.get("destination", "")

        prompt = (
            f"Research hotels for: {request.task}\n"
            f"Destination: {destination}\n\n"
            "Provide recommendations including:\n"
            "1. Top hotel options (include FHR-eligible properties if possible)\n"
            "2. Neighborhood recommendations\n"
            "3. Price ranges\n"
            "4. **Amex Platinum FHR benefits**: If any recommended hotels are in the "
            "Fine Hotels + Resorts portfolio, highlight: room upgrade, free breakfast, "
            "$100 property credit, 4pm late checkout\n"
            "5. Marriott/Hilton Gold status benefits at relevant properties\n\n"
            "Format for Telegram Markdown."
        )

        response = self._anthropic.messages.create(
            model=TRAVEL_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._ok(request, result=response.content[0].text)

    async def _handle_trip_planning(self, request: AgentRequest) -> AgentResponse:
        """Full trip itinerary planning."""
        context = request.context

        prompt = (
            f"Plan a trip: {request.task}\n"
            f"Additional context: {context}\n\n"
            "Create a comprehensive trip plan including:\n"
            "1. **Itinerary overview** — day-by-day highlights\n"
            "2. **Flights** — recommended routes/airlines, book directly or amextravel.com (5x points)\n"
            "3. **Hotels** — top options, note any FHR-eligible properties for Amex Platinum benefits\n"
            "4. **Activities** — must-do experiences, reservations needed\n"
            "5. **Amex Platinum optimization**:\n"
            "   - Which bookings earn 5x points\n"
            "   - FHR hotel benefits if applicable\n"
            "   - Lounge access at departure/arrival airports\n"
            "   - Relevant insurance coverage\n"
            "6. **Practical tips** — best time to book, local transport, currency\n\n"
            "Format clearly for Telegram Markdown. Be specific and actionable."
        )

        response = self._anthropic.messages.create(
            model=TRAVEL_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        result = response.content[0].text

        # Add lounge info if we have context
        origin = context.get("origin", "")
        destination = context.get("destination", "")
        if origin and destination:
            perks = format_trip_perks(
                origin=origin.upper()[:3],
                destination=destination.upper()[:3],
                hotel_name=context.get("hotel"),
                is_fhr=context.get("is_fhr", False),
            )
            result = f"{result}\n\n{perks}"

        return self._ok(request, result=result)

    async def _handle_lounge_lookup(self, request: AgentRequest) -> AgentResponse:
        """Look up lounge access at an airport."""
        context = request.context
        airport = context.get("airport") or ""

        # Try to extract airport code from task
        if not airport:
            import re
            codes = re.findall(r"\b([A-Z]{3})\b", request.task.upper())
            airport = codes[0] if codes else ""

        if not airport:
            return self._error(request, "Please specify an airport code (e.g., JFK, LAX, LHR).")

        lounges = get_lounge_access(airport.upper()[:3])
        if lounges:
            lines = [f"✈️ *Amex Platinum Lounges at {airport.upper()}*\n"]
            lines.extend(lounges)
            result = "\n".join(lines)
        else:
            result = (
                f"No Centurion Lounge at {airport.upper()}, but your Priority Pass "
                f"gives access to 1,300+ lounges worldwide. Check prioritypass.com for options."
            )

        return self._ok(request, result=result)

    async def _handle_perks_query(self, request: AgentRequest) -> AgentResponse:
        """Answer questions about credit card perks."""
        context = request.context
        cards = get_credit_cards()

        # Include Amex Platinum details in the prompt
        benefits_text = "\n".join(
            f"- {b.name}: {b.value} — {b.description}"
            for b in AMEX_PLATINUM.benefits
        )

        prompt = (
            f"Question about credit card perks: {request.task}\n\n"
            f"User's Amex Platinum benefits:\n{benefits_text}\n\n"
            f"User's configured cards: {[c.get('name') for c in cards]}\n\n"
            "Answer the question accurately and specifically. "
            "If asking about maximizing benefits for a purchase, give a clear recommendation. "
            "Format for Telegram Markdown."
        )

        response = self._anthropic.messages.create(
            model=TRAVEL_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._ok(request, result=response.content[0].text)

    async def _handle_general_travel(self, request: AgentRequest) -> AgentResponse:
        """Handle general travel queries."""
        response = self._anthropic.messages.create(
            model=TRAVEL_MODEL,
            max_tokens=2048,
            system=(
                "You are a travel planning expert with deep knowledge of credit card benefits, "
                "especially Amex Platinum. Give practical, actionable advice. "
                "Format for Telegram Markdown."
            ),
            messages=[{"role": "user", "content": request.task}],
        )
        return self._ok(request, result=response.content[0].text)


# FastAPI app entry point
_agent = TravelAgent()
app = _agent.app
