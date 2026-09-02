from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.db.base import SessionLocal
from app.db.models import AgentRun, ErrorLog


@dataclass
class RunHandle:
    run_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    provider: str | None = None
    model: str | None = None
    _extra: dict = field(default_factory=dict)

    def record_usage(self, *, input_tokens: int = 0, output_tokens: int = 0,
                     estimated_cost: float = 0.0, provider: str | None = None,
                     model: str | None = None) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.estimated_cost += estimated_cost
        if provider:
            self.provider = provider
        if model:
            self.model = model


@contextmanager
def agent_run(*, campaign_id: str, agent_name: str, prompt_version: str | None = None,
              provider: str | None = None, model: str | None = None):
    """Log one agent execution in its OWN transaction so a FAILED status
    survives the pipeline session rollback."""
    s1 = SessionLocal()
    try:
        row = AgentRun(
            campaign_id=campaign_id, agent_name=agent_name, prompt_version=prompt_version,
            provider=provider, model=model, status="RUNNING",
        )
        s1.add(row)
        s1.commit()
        run_id = row.id
    finally:
        s1.close()

    handle = RunHandle(run_id=run_id, provider=provider, model=model)
    try:
        yield handle
    except Exception as e:  # noqa: BLE001 - re-raised below
        _finish(run_id, handle, status="FAILED", exc=e, campaign_id=campaign_id, agent_name=agent_name)
        raise
    else:
        _finish(run_id, handle, status="SUCCESS", exc=None, campaign_id=campaign_id, agent_name=agent_name)


def _finish(run_id: str, handle: RunHandle, *, status: str, exc: Exception | None,
            campaign_id: str, agent_name: str) -> None:
    s = SessionLocal()
    try:
        row = s.get(AgentRun, run_id)
        if row is None:
            return
        row.status = status
        row.finished_at = datetime.now(timezone.utc)
        row.input_tokens = handle.input_tokens
        row.output_tokens = handle.output_tokens
        row.estimated_cost = handle.estimated_cost
        row.provider = handle.provider
        row.model = handle.model
        if exc is not None:
            row.error_type = getattr(exc, "error_type", type(exc).__name__)
            row.error_message = str(exc)[:2000]
            s.add(ErrorLog(
                campaign_id=campaign_id, scope=f"agent:{agent_name}",
                error_type=row.error_type, message=str(exc)[:2000],
            ))
        s.commit()
    finally:
        s.close()
