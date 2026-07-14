"""Provider boundary for flow discovery and quiz session creation."""

from __future__ import annotations

from typing import Protocol

from .base import QuizSession
from .models import FlowSummary


class QuizProvider(Protocol):
    async def list_flows(self) -> tuple[FlowSummary, ...]: ...

    async def active_flow(self) -> FlowSummary: ...

    async def select_flow(self, flow_id: str) -> FlowSummary: ...

    async def create_session(self, flow_id: str) -> QuizSession: ...

    async def close(self) -> None: ...
