"""
Shared Pydantic models used across the orchestrator and sub-agents.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    FINANCE = "finance"
    CALENDAR = "calendar"
    RESEARCH = "research"
    BROWSER = "browser"
    TRAVEL = "travel"
    MARKET_INTELLIGENCE = "market_intelligence"


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ── Internal API ─────────────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    """What Apollo sends to a sub-agent."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task: str                           # Natural-language task description
    context: dict[str, Any] = Field(default_factory=dict)  # Relevant context
    user_id: int                        # Telegram user ID (for confirmations)
    conversation_id: str                # Ties back to the conversation


class AgentResponse(BaseModel):
    """What a sub-agent returns to Apollo."""
    request_id: str
    agent: AgentName
    success: bool
    result: Optional[str] = None        # Natural-language result summary
    data: dict[str, Any] = Field(default_factory=dict)  # Structured data
    error: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_id: Optional[str] = None  # If confirmation needed


# ── Confirmation Gate ─────────────────────────────────────────────────────────

class ConfirmationRequest(BaseModel):
    """A pending action awaiting user approval."""
    confirmation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int
    conversation_id: str
    agent: AgentName
    action_description: str             # Human-readable description shown to user
    action_payload: dict[str, Any]      # Serialized action to execute on approval
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    status: ConfirmationStatus = ConfirmationStatus.PENDING


# ── Memory ───────────────────────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    """A single message stored in conversation history."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    user_id: int
    role: MessageRole
    content: str
    agent: Optional[AgentName] = None   # Which agent produced this (if assistant)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryEntry(BaseModel):
    """A long-term memory entry with optional semantic embedding."""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int
    category: str                       # e.g. "preference", "fact", "event"
    content: str                        # Human-readable memory text
    embedding: Optional[list[float]] = None  # pgvector embedding
    source_conversation_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


# ── TradingView ───────────────────────────────────────────────────────────────

class TradingViewAlert(BaseModel):
    """Parsed TradingView webhook payload."""
    ticker: str
    exchange: Optional[str] = None
    price: Optional[float] = None
    alert_name: Optional[str] = None
    message: Optional[str] = None
    time: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


# ── Calendar ──────────────────────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    """Normalized calendar event across providers."""
    event_id: Optional[str] = None
    provider: str
    account: str
    title: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: list[str] = Field(default_factory=list)
    url: Optional[str] = None


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditEntry(BaseModel):
    """An append-only audit log entry."""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: int
    agent: AgentName
    action: str                         # e.g. "create_calendar_event"
    details: dict[str, Any] = Field(default_factory=dict)
    confirmed_by_user: bool = False
    confirmation_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
