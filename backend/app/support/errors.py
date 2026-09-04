"""Normalised support error codes + human-readable suggested actions (Phase 10
§65-§66). Maps the internal retry taxonomy / scopes to a stable, user-facing code
and a one-line "do this next"."""
from __future__ import annotations

# stable code -> (matcher hints, suggested action in Korean)
_ACTIONS: dict[str, str] = {
    "OLLAMA_UNAVAILABLE": "Ollama가 실행 중인지 확인하세요 (`ollama serve`). 로컬 모델이 꺼져 있으면 클라우드 폴백 설정을 확인하세요.",
    "MODEL_OUTPUT_SCHEMA_INVALID": "모델이 형식에 맞지 않는 응답을 반환했습니다. 자동으로 다음 엔진으로 승급됩니다 — 반복되면 품질 프리셋을 높이세요.",
    "PROVIDER_RATE_LIMITED": "제공자가 요청을 제한하고 있습니다. 자동 재시도(백오프) 상태를 확인하세요.",
    "VIDEO_PROVIDER_TIMEOUT": "영상 제공자 응답이 지연됩니다. 자동 재시도 상태를 확인하고, 계속되면 장면 수를 줄이세요.",
    "DB_CONNECTION_FAILED": "데이터베이스 상태를 확인하세요. 컨테이너/네트워크 재시작 후 자동 재연결됩니다.",
    "REDIS_UNAVAILABLE": "Redis 상태를 확인하세요. 큐 작업은 Redis 복구 후 재개됩니다.",
    "RENDER_FFMPEG_FAILED": "렌더 입력(에셋 누락/손상)을 확인하세요. 실패 장면만 재렌더됩니다.",
    "STORAGE_WRITE_FAILED": "스토리지 쓰기에 실패했습니다. 디스크 여유 공간과 권한을 확인하세요.",
    "PUBLISH_AUTH_EXPIRED": "SNS 계정 토큰이 만료됐습니다. 계정을 다시 연결하세요.",
    "GOVERNANCE_BLOCKED": "거버넌스가 게시를 차단했습니다. 검수 센터에서 사유를 확인하고 수정/승인하세요.",
    "BUDGET_EXCEEDED": "예산 한도에 도달했습니다. 한도를 올리거나 다음 주기를 기다리세요. 완료된 결과물은 보존됩니다.",
    "PLATFORM_DISABLED": "해당 플랫폼이 꺼져 있습니다. SNS 선택에서 활성화하세요.",
    "WORKER_STALLED": "작업자가 응답하지 않습니다. 작업자를 재시작하거나 멈춘 작업 스캔을 실행하세요.",
    "INSUFFICIENT_RESEARCH": "충분한 근거 출처를 찾지 못했습니다. 주제를 구체화하거나 참고 URL을 추가하세요.",
    "PUBLISH_PAUSED": "전역 게시 일시정지가 켜져 있습니다. 운영 화면에서 해제하세요.",
    "PAID_PROVIDER_PAUSED": "전역 유료 제공자 일시정지가 켜져 있습니다. 로컬 작업만 진행됩니다.",
    "GOOGLE_NOT_CONFIGURED": "GOOGLE_API_KEY가 설정되지 않았습니다. .env에 키를 넣고 IMAGE_PROVIDER/VIDEO_PROVIDER를 google로 설정하세요.",
    "GOOGLE_AUTH_FAILED": "Google API 키가 거부됐습니다. 키 값과 사용 설정(Generative Language API 활성화)을 확인하세요.",
    "GOOGLE_RATE_LIMITED": "Google API 요청 한도에 도달했습니다. 자동 재시도 상태를 확인하고 잠시 후 다시 시도하세요.",
    "GOOGLE_PROVIDER_ERROR": "Google 이미지/영상 생성에 실패했습니다. 모델명(설정값)과 API 응답을 확인하세요.",
    "ELEVENLABS_NOT_CONFIGURED": "ELEVENLABS_API_KEY(또는 ELEVENLABS_VOICE_ID)가 설정되지 않았습니다.",
    "ELEVENLABS_AUTH_FAILED": "ElevenLabs API 키가 거부됐습니다. 키 값과 구독 상태를 확인하세요.",
    "ELEVENLABS_PERMISSION_REQUIRED": "ElevenLabs API 키 설정에서 Voices: Read와 Text to Speech 권한을 켜세요.",
    "ELEVENLABS_RATE_LIMITED": "ElevenLabs 요청 한도에 도달했습니다. 자동 재시도 상태를 확인하세요.",
    "ELEVENLABS_PROVIDER_ERROR": "ElevenLabs 음성 합성에 실패했습니다. voice_id와 model_id 설정을 확인하세요.",
    "UNKNOWN": "AI 지원 스냅샷을 캡처해 관리자 또는 기술 지원에 전달하세요.",
}

# internal error_type / scope fragments -> stable code
_MAP: list[tuple[tuple[str, ...], str]] = [
    # vendor-specific codes first (they arrive as `provider_code` on ProviderError)
    (("google_not_configured",), "GOOGLE_NOT_CONFIGURED"),
    (("google_auth_failed",), "GOOGLE_AUTH_FAILED"),
    (("google_rate_limited",), "GOOGLE_RATE_LIMITED"),
    (("google_provider_error", "google_timeout"), "GOOGLE_PROVIDER_ERROR"),
    (("elevenlabs_not_configured",), "ELEVENLABS_NOT_CONFIGURED"),
    (("elevenlabs_auth_failed",), "ELEVENLABS_AUTH_FAILED"),
    (("elevenlabs_permission_required", "voices_read"), "ELEVENLABS_PERMISSION_REQUIRED"),
    (("elevenlabs_rate_limited",), "ELEVENLABS_RATE_LIMITED"),
    (("elevenlabs_provider_error", "elevenlabs_timeout"), "ELEVENLABS_PROVIDER_ERROR"),
    (("ollama", "local model", "local_model"), "OLLAMA_UNAVAILABLE"),
    (("invalid_output", "schema_invalid", "invalid json"), "MODEL_OUTPUT_SCHEMA_INVALID"),
    (("rate_limit", "429", "ratelimited"), "PROVIDER_RATE_LIMITED"),
    (("video", "render provider"), "VIDEO_PROVIDER_TIMEOUT"),
    (("db_connection", "operationalerror", "could not connect", "psycopg"), "DB_CONNECTION_FAILED"),
    (("redis",), "REDIS_UNAVAILABLE"),
    (("ffmpeg", "render_ffmpeg"), "RENDER_FFMPEG_FAILED"),
    (("storage_write", "no space", "disk"), "STORAGE_WRITE_FAILED"),
    (("auth_error", "token", "reauth", "expired"), "PUBLISH_AUTH_EXPIRED"),
    (("governance", "blocked"), "GOVERNANCE_BLOCKED"),
    (("budget",), "BUDGET_EXCEEDED"),
    (("platform_deselected", "platform disabled"), "PLATFORM_DISABLED"),
    (("stalled", "stall", "lease"), "WORKER_STALLED"),
    (("insufficient_research",), "INSUFFICIENT_RESEARCH"),
    (("global_publish_pause", "publish_paused"), "PUBLISH_PAUSED"),
    (("paid_provider_pause",), "PAID_PROVIDER_PAUSED"),
]

_RETRYABLE = {"PROVIDER_RATE_LIMITED", "VIDEO_PROVIDER_TIMEOUT", "DB_CONNECTION_FAILED",
              "REDIS_UNAVAILABLE", "MODEL_OUTPUT_SCHEMA_INVALID",
              "GOOGLE_RATE_LIMITED", "ELEVENLABS_RATE_LIMITED"}


def normalise(error_type: str | None, message: str | None = "", scope: str | None = "") -> str:
    blob = " ".join(x for x in (error_type or "", message or "", scope or "") if x).lower()
    if not blob.strip():
        return "UNKNOWN"
    for needles, code in _MAP:
        if any(n in blob for n in needles):
            return code
    et = (error_type or "").upper().strip()
    return et if et in _ACTIONS else "UNKNOWN"


def suggested_action(code: str) -> str:
    return _ACTIONS.get(code, _ACTIONS["UNKNOWN"])


def is_retryable(code: str) -> bool:
    return code in _RETRYABLE
