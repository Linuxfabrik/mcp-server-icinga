# SPDX-License-Identifier: Unlicense

"""Icinga 2 Core REST API backend.

A thin synchronous client around the Icinga 2 Core REST API (port 5665)
plus the helpers that turn raw object-query results into the compact,
LLM-friendly summaries the MCP tools return.
"""

from __future__ import annotations

from mcp_server_icinga.icinga2_core.client import (
    HOST_STATE_CODES,
    HOST_STATES,
    SERVICE_STATE_CODES,
    SERVICE_STATES,
    Icinga2CoreAuthError,
    Icinga2CoreClient,
    Icinga2CoreError,
    Icinga2CoreNotFoundError,
    summarize_host,
    summarize_service,
)

__all__ = [
    'HOST_STATES',
    'HOST_STATE_CODES',
    'SERVICE_STATES',
    'SERVICE_STATE_CODES',
    'Icinga2CoreAuthError',
    'Icinga2CoreClient',
    'Icinga2CoreError',
    'Icinga2CoreNotFoundError',
    'summarize_host',
    'summarize_service',
]
