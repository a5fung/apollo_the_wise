"""
Append-only audit log.
Every action taken by any agent is recorded here — cannot be modified or deleted.
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from shared.models import AgentName, AuditEntry

logger = logging.getLogger(__name__)

# File-based audit log (append-only)
AUDIT_LOG_PATH = Path("audit.log")

# In-memory lock to prevent interleaved writes
_write_lock = asyncio.Lock()


async def log_action(
    user_id: int,
    agent: AgentName,
    action: str,
    details: dict[str, Any] | None = None,
    confirmed_by_user: bool = False,
    confirmation_id: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> AuditEntry:
    """
    Record an action to the append-only audit log.
    Returns the created AuditEntry.
    """
    entry = AuditEntry(
        user_id=user_id,
        agent=agent,
        action=action,
        details=details or {},
        confirmed_by_user=confirmed_by_user,
        confirmation_id=confirmation_id,
        success=success,
        error=error,
    )

    line = json.dumps(entry.model_dump(mode="json"), default=str) + "\n"

    async with _write_lock:
        try:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            # Log to stderr but never let audit failure crash the main flow
            logger.error(f"Failed to write audit log: {e}")

    logger.info(
        f"AUDIT | agent={agent.value} action={action} "
        f"user={user_id} success={success} confirmed={confirmed_by_user}"
    )
    return entry


def read_audit_log(
    limit: int = 100,
    user_id: Optional[int] = None,
    agent: Optional[AgentName] = None,
) -> list[AuditEntry]:
    """Read recent entries from the audit log (newest first)."""
    if not AUDIT_LOG_PATH.exists():
        return []

    entries: list[AuditEntry] = []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = AuditEntry(**data)
                if user_id is not None and entry.user_id != user_id:
                    continue
                if agent is not None and entry.agent != agent:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
            except (json.JSONDecodeError, ValueError):
                continue
    except OSError:
        pass

    return entries
