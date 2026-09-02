# Incident Response (Phase 10 §22, §102)

## First move for any incident
1. Open the dashboard → **AI 지원 스냅샷** (`/support`).
2. **[캡처 모드]** → screenshot, or **[지원 정보 복사]** → paste into ChatGPT / send to admin.
3. Read `overall_health`, `last_error.error_code`, and `suggested_action`.

## Kill switches (DB-backed, survive restart) — `app/ops/runtime_flags.py`
| Switch | Effect | Toggle |
|---|---|---|
| `GLOBAL_PUBLISH_PAUSE` | no remote publish on any platform; jobs stay READY | `POST /api/ops/flags/GLOBAL_PUBLISH_PAUSE {enabled,confirm}` |
| `GLOBAL_PAID_PROVIDER_PAUSE` | no cloud/paid provider calls; local Ollama + deterministic work continue | `POST /api/ops/flags/GLOBAL_PAID_PROVIDER_PAUSE` |
| `EMERGENCY_STOP` | autopilot halt + publish pause | existing Phase 4 control |
| `SAFE_MODE` | no new autopilot production | `POST /api/ops/flags/SAFE_MODE` |
| `MAINTENANCE_MODE` | readiness → not ready | `POST /api/ops/flags/MAINTENANCE_MODE` |
| Channel pause | per-channel stop | `POST /api/channels/{id}/pause` |

All are reachable from mobile (`/support`, `/admin`).

## Playbooks
See `docs/OPERATIONS_RUNBOOK.md` for: backend / worker / Redis / DB / Ollama /
provider outage / render failure / storage / SNS auth expiry / publish failure /
stuck campaign / budget block / governance block / backup-restore.

## Escalation
If the Support Snapshot's `suggested_action` doesn't resolve it: capture the
snapshot (screenshot + copied text, both secret-free) and the `trace_id`, and
open a ticket with them.
