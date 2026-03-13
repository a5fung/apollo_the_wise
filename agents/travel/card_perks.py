"""
Credit card perks knowledge base and optimization engine.
Knows about card benefits and recommends the best card for each travel scenario.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class CardBenefit:
    name: str
    description: str
    value: str  # e.g. "$200/year", "5x points", "complimentary"
    category: str  # lounge, hotel, flight, dining, insurance, etc.
    annual_limit: Optional[str] = None
    expires: Optional[str] = None  # "Dec 31" or "anniversary year"


@dataclass
class CreditCard:
    name: str
    card_type: str
    annual_fee: int
    benefits: list[CardBenefit] = field(default_factory=list)
    point_multipliers: dict[str, float] = field(default_factory=dict)


# ── Amex Platinum Benefits Knowledge Base ────────────────────────────────────

AMEX_PLATINUM = CreditCard(
    name="American Express Platinum",
    card_type="amex_platinum",
    annual_fee=695,
    point_multipliers={
        "flights_direct": 5.0,    # 5x on flights booked directly or via Amex Travel
        "amex_travel_portal": 5.0,
        "hotels_amex_travel": 5.0,
        "default": 1.0,
    },
    benefits=[
        CardBenefit(
            name="Centurion Lounge Access",
            description="Complimentary access to Amex Centurion Lounges worldwide",
            value="Complimentary",
            category="lounge",
        ),
        CardBenefit(
            name="Priority Pass Select",
            description="Access to 1,300+ airport lounges via Priority Pass",
            value="Complimentary",
            category="lounge",
        ),
        CardBenefit(
            name="Delta Sky Club Access",
            description="10 complimentary Delta Sky Club visits per year when flying Delta",
            value="10 visits/year",
            category="lounge",
            annual_limit="10 visits",
        ),
        CardBenefit(
            name="Fine Hotels + Resorts (FHR)",
            description=(
                "Book through Amex FHR for: room upgrade on arrival, "
                "daily breakfast for two, guaranteed 4pm late checkout, "
                "noon check-in when available, $100 property credit, "
                "complimentary Wi-Fi"
            ),
            value="Up to $600+ in value per stay",
            category="hotel",
        ),
        CardBenefit(
            name="Hotel Collection",
            description="$100 credit on qualifying charges at The Hotel Collection properties (2+ night stay)",
            value="$100 credit per stay",
            category="hotel",
        ),
        CardBenefit(
            name="Airline Fee Credit",
            description="Up to $200 in statement credits per calendar year for incidental fees at one selected airline",
            value="$200/year",
            category="flight",
            annual_limit="$200/calendar year",
            expires="Dec 31",
        ),
        CardBenefit(
            name="Uber Cash",
            description="$15 in Uber Cash monthly ($20 in December) for Uber rides or Uber Eats",
            value="$200/year ($15/mo + $20 Dec)",
            category="travel",
            annual_limit="$200/year",
        ),
        CardBenefit(
            name="Saks Fifth Avenue Credit",
            description="Up to $100 in credits at Saks ($50 Jan-Jun, $50 Jul-Dec)",
            value="$100/year",
            category="shopping",
            annual_limit="$100/year",
        ),
        CardBenefit(
            name="Marriott Bonvoy Gold Status",
            description="Complimentary Marriott Bonvoy Gold Elite status",
            value="Gold status",
            category="hotel",
        ),
        CardBenefit(
            name="Hilton Honors Gold Status",
            description="Complimentary Hilton Honors Gold status",
            value="Gold status",
            category="hotel",
        ),
        CardBenefit(
            name="Global Entry / TSA PreCheck Credit",
            description="Up to $100 credit for Global Entry (or $85 for TSA PreCheck) every 4.5 years",
            value="$100 every 4.5 years",
            category="travel",
        ),
        CardBenefit(
            name="Car Rental Insurance",
            description="Premium car rental protection when you pay with the card and decline the rental agency CDW",
            value="Coverage up to $75,000",
            category="insurance",
        ),
        CardBenefit(
            name="Trip Delay Insurance",
            description="Up to $500 per trip for expenses if trip is delayed 6+ hours",
            value="$500/trip",
            category="insurance",
        ),
        CardBenefit(
            name="Trip Cancellation/Interruption Insurance",
            description="Up to $10,000 per trip for non-refundable expenses",
            value="$10,000/trip",
            category="insurance",
        ),
        CardBenefit(
            name="Baggage Insurance",
            description="Coverage for lost/damaged/stolen baggage",
            value="$2,000 checked / $3,000 carry-on",
            category="insurance",
        ),
        CardBenefit(
            name="International Airline Program",
            description="Access to discounted business/first class fares on premium airlines",
            value="Discounted premium fares",
            category="flight",
        ),
        CardBenefit(
            name="No Foreign Transaction Fees",
            description="0% foreign transaction fees on all purchases abroad",
            value="No fee",
            category="international",
        ),
        CardBenefit(
            name="Equinox Credit",
            description="Up to $300/year in statement credits for Equinox memberships",
            value="$300/year",
            category="fitness",
            annual_limit="$300/year",
        ),
        CardBenefit(
            name="CLEAR Plus Credit",
            description="Up to $189/year for CLEAR Plus membership",
            value="$189/year",
            category="travel",
            annual_limit="$189/year",
        ),
        CardBenefit(
            name="Digital Entertainment Credit",
            description="Up to $20/month for Disney+, Hulu, ESPN+, The New York Times, Peacock",
            value="$240/year",
            category="entertainment",
            annual_limit="$240/year",
        ),
    ],
)


# ── Lounge database ───────────────────────────────────────────────────────────

CENTURION_LOUNGES: dict[str, list[str]] = {
    "ATL": ["ATL Centurion Lounge - Concourse F"],
    "BOS": ["BOS Centurion Lounge - Terminal B"],
    "CLT": ["CLT Centurion Lounge - Concourse E"],
    "DAL": ["DAL Centurion Lounge - Lemmon Ave"],
    "DFW": ["DFW Centurion Lounge - Terminal D"],
    "DEN": ["DEN Centurion Lounge - Concourse C"],
    "EWR": ["EWR Centurion Lounge - Terminal C"],
    "HKG": ["HKG Centurion Lounge"],
    "HNL": ["HNL Centurion Lounge - Main Terminal"],
    "IAH": ["IAH Centurion Lounge - Terminal D"],
    "JFK": ["JFK Centurion Lounge - Terminal 4"],
    "LAS": ["LAS Centurion Lounge - Concourse D"],
    "LAX": ["LAX Centurion Lounge - TBIT"],
    "LGA": ["LGA Centurion Lounge - Terminal B"],
    "MIA": ["MIA Centurion Lounge - Concourse D"],
    "MSP": ["MSP Centurion Lounge - Concourse G"],
    "PHL": ["PHL Centurion Lounge - Terminal A"],
    "PHX": ["PHX Centurion Lounge - Concourse B"],
    "SEA": ["SEA Centurion Lounge - North Satellite"],
    "SFO": ["SFO Centurion Lounge - Terminal 3"],
}


# ── Optimization functions ────────────────────────────────────────────────────

def get_lounge_access(airport_code: str) -> list[str]:
    """Get available lounges at an airport for Amex Platinum holders."""
    code = airport_code.upper()
    lounges = []

    centurion = CENTURION_LOUNGES.get(code)
    if centurion:
        lounges.extend([f"🏛 Centurion Lounge: {l}" for l in centurion])

    # Priority Pass covers 1,300+ lounges globally — note it's available everywhere
    lounges.append("✈️ Priority Pass: Available at most major airports (1,300+ lounges)")

    return lounges


def recommend_card_for_booking(
    booking_type: str,  # "flight", "hotel", "hotel_fhr", "car", "amex_travel"
    amount: float,
    cards: list[CreditCard],
) -> dict[str, Any]:
    """Recommend the best card for a given booking type and amount."""
    recommendations = []

    for card in cards:
        multiplier = card.point_multipliers.get(booking_type, card.point_multipliers.get("default", 1.0))
        points_earned = int(amount * multiplier)
        relevant_benefits = [
            b for b in card.benefits
            if booking_type in b.category or "insurance" in b.category
        ]

        recommendations.append({
            "card": card.name,
            "multiplier": multiplier,
            "points_earned": points_earned,
            "relevant_benefits": [
                {"name": b.name, "value": b.value} for b in relevant_benefits
            ],
        })

    # Sort by points earned
    recommendations.sort(key=lambda r: r["points_earned"], reverse=True)
    return recommendations[0] if recommendations else {}


def format_trip_perks(
    origin: str,
    destination: str,
    hotel_name: str | None = None,
    is_fhr: bool = False,
) -> str:
    """Format applicable Amex Platinum perks for a specific trip."""
    lines = ["💳 *Amex Platinum Benefits for This Trip*\n"]

    # Lounge access at origin
    origin_lounges = get_lounge_access(origin)
    if origin_lounges:
        lines.append(f"🛫 *Lounges at {origin}:*")
        lines.extend([f"  {l}" for l in origin_lounges])
        lines.append("")

    # Lounge access at destination
    dest_lounges = get_lounge_access(destination)
    if dest_lounges:
        lines.append(f"🛬 *Lounges at {destination}:*")
        lines.extend([f"  {l}" for l in dest_lounges])
        lines.append("")

    # Hotel benefits
    if is_fhr and hotel_name:
        lines.append(f"🏨 *FHR Benefits at {hotel_name}:*")
        lines.append("  • Room upgrade on arrival (when available)")
        lines.append("  • Complimentary daily breakfast for two")
        lines.append("  • $100 property credit")
        lines.append("  • Guaranteed 4pm late checkout")
        lines.append("  • Noon early check-in when available")
        lines.append("  • Complimentary Wi-Fi")
        lines.append("")
    elif hotel_name:
        lines.append(f"🏨 *Hotel Status Benefits at {hotel_name}:*")
        lines.append("  • Marriott Gold: 25% bonus points, room upgrade requests")
        lines.append("  • Hilton Gold: 80% bonus points, complimentary breakfast at select properties")
        lines.append("")

    # Insurance reminders
    lines.append("🛡 *Insurance Coverage:*")
    lines.append("  • Trip Delay: up to $500 if delayed 6+ hours")
    lines.append("  • Baggage: $2K checked / $3K carry-on")
    lines.append("  • Car Rental: up to $75K (decline CDW at counter)")

    # Booking tip
    lines.append("\n💡 *Tip:* Book flights directly or via amextravel.com for 5x points.")

    return "\n".join(lines)
