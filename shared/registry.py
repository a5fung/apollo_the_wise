"""
Integration Registry — reads integrations.yaml and exposes active providers.
Apollo queries this to know what capabilities are available at runtime.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path("integrations.yaml")


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    """Load and cache integrations.yaml."""
    if not REGISTRY_PATH.exists():
        logger.warning(f"integrations.yaml not found at {REGISTRY_PATH.absolute()}")
        return {}
    with open(REGISTRY_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def reload_registry() -> dict[str, Any]:
    """Force reload (clears cache)."""
    load_registry.cache_clear()
    return load_registry()


def get_calendar_providers() -> list[dict[str, Any]]:
    """Return active calendar provider configs."""
    registry = load_registry()
    providers = registry.get("calendar", [])
    return [p for p in providers if p.get("enabled", True)]


def get_finance_providers() -> list[dict[str, Any]]:
    """Return active finance provider configs."""
    registry = load_registry()
    providers = registry.get("finance", [])
    return [p for p in providers if p.get("enabled", True)]


def get_research_providers() -> list[dict[str, Any]]:
    """Return active research provider configs."""
    registry = load_registry()
    providers = registry.get("research", [])
    return [p for p in providers if p.get("enabled", True)]


def get_agent_url(agent_name: str) -> Optional[str]:
    """Get the HTTP URL for a sub-agent by name."""
    registry = load_registry()
    agents = registry.get("agents", {})
    agent_config = agents.get(agent_name, {})
    if not agent_config.get("enabled", True):
        return None
    return agent_config.get("url")


def get_credit_cards() -> list[dict[str, Any]]:
    """Return configured credit cards for travel optimization."""
    registry = load_registry()
    return registry.get("travel", {}).get("credit_cards", [])


def get_active_agents() -> list[str]:
    """Return names of all enabled agents."""
    registry = load_registry()
    agents = registry.get("agents", {})
    return [name for name, cfg in agents.items() if cfg.get("enabled", True)]


def get_provider_credential(provider_config: dict[str, Any]) -> Optional[str]:
    """Resolve a credential from env using credentials_env key."""
    env_var = provider_config.get("credentials_env")
    if not env_var:
        return None
    return os.environ.get(env_var)
