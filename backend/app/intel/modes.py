"""Execution modes + the LEARN_ONLY / REFERENCE_ONLY production kill-switch.

CREATE_ONLY          — existing content production only, no reference learning.
CREATE_AND_LEARN     — reference analysis + learning + content production (UI default).
LEARN_ONLY           — learning only. NEVER: campaign production, AI image/video,
                       TTS, final render, PublishJob, SNS API call.
REFERENCE_ONLY       — store references in the library only; no automatic
                       Production Memory update.
"""
from __future__ import annotations

from enum import Enum


class ExecutionMode(str, Enum):
    CREATE_ONLY = "CREATE_ONLY"
    CREATE_AND_LEARN = "CREATE_AND_LEARN"
    LEARN_ONLY = "LEARN_ONLY"
    REFERENCE_ONLY = "REFERENCE_ONLY"


_PRODUCES_CONTENT = {ExecutionMode.CREATE_ONLY, ExecutionMode.CREATE_AND_LEARN}
_LEARNS = {ExecutionMode.CREATE_AND_LEARN, ExecutionMode.LEARN_ONLY}
# REFERENCE_ONLY stores the reference but does NOT feed Production Memory / datasets automatically
_WRITES_LEARNING_OUTPUT = {ExecutionMode.CREATE_AND_LEARN, ExecutionMode.LEARN_ONLY}


class ProductionSideEffectBlocked(RuntimeError):
    """Raised when a LEARN_ONLY / REFERENCE_ONLY run tries to do production work."""


def resolve_execution_mode(value, *, default: ExecutionMode = ExecutionMode.CREATE_AND_LEARN) -> ExecutionMode:
    if isinstance(value, ExecutionMode):
        return value
    if not value:
        return default
    try:
        return ExecutionMode(str(value).strip().upper())
    except ValueError:
        return default


def produces_content(mode) -> bool:
    return resolve_execution_mode(mode) in _PRODUCES_CONTENT


def does_learning(mode) -> bool:
    return resolve_execution_mode(mode) in _LEARNS


def writes_learning_output(mode) -> bool:
    return resolve_execution_mode(mode) in _WRITES_LEARNING_OUTPUT


def is_learn_only(mode) -> bool:
    return resolve_execution_mode(mode) in (ExecutionMode.LEARN_ONLY, ExecutionMode.REFERENCE_ONLY)


# operations that MUST NOT run under LEARN_ONLY / REFERENCE_ONLY (spec §B, §CJ)
BLOCKED_OPERATIONS = (
    "campaign_production", "ai_image_generation", "ai_video_generation",
    "tts_production", "final_render", "publish_job", "sns_api_call",
)


def assert_no_production_side_effects(mode, operation: str) -> None:
    """Call this at the top of every production entry point that a learning run
    could reach. Raises ProductionSideEffectBlocked under LEARN_ONLY/REFERENCE_ONLY."""
    if is_learn_only(mode):
        raise ProductionSideEffectBlocked(
            f"operation {operation!r} is not allowed in {resolve_execution_mode(mode).value} mode"
        )
