"""
Base sub-agent class.

Every sub-agent:
1. Runs as a FastAPI service
2. Implements POST /task -> AgentResponse
3. Implements GET /health
4. Verifies the Apollo internal API secret on every request

Sub-agents never communicate with each other — only through Apollo.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader

from shared.audit import log_action
from shared.models import AgentName, AgentRequest, AgentResponse
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-Apollo-Secret", auto_error=True)


def verify_internal_secret(api_key: str = Depends(_api_key_header)) -> str:
    """FastAPI dependency — reject requests without the internal API secret."""
    expected = get_secrets().internal_api_secret
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API secret",
        )
    return api_key


class BaseAgent(ABC):
    """
    Abstract base class for all Apollo sub-agents.

    Subclasses must implement `execute_task`.
    """

    def __init__(self, agent_name: AgentName) -> None:
        self.agent_name = agent_name
        self.app = FastAPI(
            title=f"Apollo {agent_name.value.title()} Agent",
            docs_url=None,
            redoc_url=None,
        )
        self._register_routes()

    def _register_routes(self) -> None:
        """Register standard routes on the FastAPI app."""

        @self.app.get("/health")
        async def health(_: str = Depends(verify_internal_secret)):
            return {"status": "ok", "agent": self.agent_name.value}

        # Unauthenticated liveness probe for Docker HEALTHCHECK. Reveals nothing
        # sensitive; a response at all means the event loop isn't deadlocked.
        @self.app.get("/live")
        async def live():
            return {"status": "ok"}

        @self.app.post("/task", response_model=AgentResponse)
        async def handle_task(
            request: AgentRequest,
            _: str = Depends(verify_internal_secret),
        ) -> AgentResponse:
            logger.info(
                f"[{self.agent_name.value}] Task: {request.task[:80]} "
                f"(user={request.user_id})"
            )
            try:
                response = await self.execute_task(request)
                await log_action(
                    user_id=request.user_id,
                    agent=self.agent_name,
                    action=f"task_completed",
                    details={
                        "task": request.task[:200],
                        "success": response.success,
                    },
                )
                return response
            except Exception as e:
                logger.exception(f"[{self.agent_name.value}] Unhandled error")
                await log_action(
                    user_id=request.user_id,
                    agent=self.agent_name,
                    action="task_failed",
                    details={"task": request.task[:200], "error": str(e)},
                    success=False,
                    error=str(e),
                )
                return AgentResponse(
                    request_id=request.request_id,
                    agent=self.agent_name,
                    success=False,
                    error=f"Internal error: {e}",
                )

    @abstractmethod
    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        """
        Process a task from Apollo and return a result.
        Subclasses implement this method.
        """
        ...

    def _ok(
        self,
        request: AgentRequest,
        result: str,
        data: dict[str, Any] | None = None,
    ) -> AgentResponse:
        """Convenience method for a successful response."""
        return AgentResponse(
            request_id=request.request_id,
            agent=self.agent_name,
            success=True,
            result=result,
            data=data or {},
        )

    def _error(self, request: AgentRequest, error: str) -> AgentResponse:
        """Convenience method for an error response."""
        return AgentResponse(
            request_id=request.request_id,
            agent=self.agent_name,
            success=False,
            error=error,
        )

    def _needs_confirmation(
        self,
        request: AgentRequest,
        description: str,
        action_payload: dict[str, Any],
        confirmation_id: str,
    ) -> AgentResponse:
        """Convenience method for a response requiring confirmation."""
        return AgentResponse(
            request_id=request.request_id,
            agent=self.agent_name,
            success=True,
            result=f"Ready to: {description}",
            requires_confirmation=True,
            confirmation_id=confirmation_id,
        )
