from __future__ import annotations

import hashlib
import json

from app.providers.base import LLMResponse
from app.providers.faults import faults


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _tokens(s: str) -> int:
    return max(1, len(s) // 4)


class MockLLMProvider:
    """Deterministic, offline LLM stand-in.

    Returns task-specific JSON derived from the supplied context so the whole
    Phase 1-A pipeline runs without any paid API. This is an explicit MOCK MODE
    implementation, not a fake of a production provider.
    """

    name = "mock"
    model = "mock-llm-v1"

    def complete(self, *, system: str, user: str, task: str, context: dict) -> LLMResponse:
        faults.maybe_raise(f"llm:{task}", "llm")
        handler = getattr(self, f"_task_{task}", None)
        if handler is None:
            payload: dict | list = {"text": f"mock response for {task}"}
        else:
            payload = handler(context)
        text = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(
            text=text,
            input_tokens=_tokens(system + user),
            output_tokens=_tokens(text),
            provider=self.name,
            model=self.model,
        )

    # --- task handlers -------------------------------------------------------

    def _task_agent_chat(self, ctx: dict) -> dict:
        role = ctx.get("agent_role", "콘텐츠 전문가")
        message = ctx.get("message", "")
        return {"reply": f"저는 {role}입니다. ‘{message[:80]}’ 요청을 확인했습니다. 현재는 모의 AI 모드이므로 실제 분석을 사용하려면 Ollama 또는 클라우드 AI를 연결해 주세요."}

    def _task_research(self, ctx: dict) -> dict:
        topic = ctx.get("topic", "the topic")
        sources = ctx.get("sources", [])
        fix_round = int(ctx.get("research_fix_count", 0))
        src_ids = [s["id"] for s in sources] or ["s1"]
        base_facts = [
            {"fact": f"{topic} 관련 핵심 사실 #1 (근거 있음)", "source_ids": src_ids[:2]},
            {"fact": f"{topic} 관련 핵심 사실 #2 (근거 있음)", "source_ids": src_ids[:1]},
            {"fact": f"{topic} 관련 통계적 주장 #1", "source_ids": src_ids[1:3] or src_ids[:1]},
        ]
        extra_facts = [
            {"fact": f"{topic} 추가 검증 사실 #{i}", "source_ids": src_ids[:2]}
            for i in range(3, 3 + fix_round * 2)
        ]
        return {
            "audience": ctx.get("audience_goal_hint", "일반 대중 / 커리어 관심층"),
            "candidate_facts": base_facts + extra_facts,
            "statistics": [f"{topic}: 관련 지표 A는 최근 3년간 상승", f"{topic}: 관련 지표 B는 지역별 편차 존재"],
            "examples": [f"{topic} 사례 1", f"{topic} 사례 2"],
            "counter_arguments": [f"{topic}에 대한 반론: 속도가 과장되었다는 시각"],
            "interesting_points": [f"{topic}에서 의외로 덜 알려진 지점"],
            "visual_opportunities": ["비교 차트", "타임라인", "before/after 카드"],
            "keywords": [topic, f"{topic} 전망", f"{topic} 대응"],
            "risk_flags": ["단정적 미래 예측 주의", "출처 편향 가능성"],
        }

    def _task_fact_check(self, ctx: dict) -> dict:
        candidates = ctx.get("candidate_facts", [])
        out = []
        for i, c in enumerate(candidates):
            fact_text = c.get("fact", "")
            has_src = bool(c.get("source_ids"))
            if not has_src:
                status, conf, reason = "UNVERIFIED", 0.2, "출처 없음"
            elif i % 5 == 4:
                status, conf, reason = "CONTRADICTED", 0.3, "출처 간 상충"
            elif i % 3 == 2:
                status, conf, reason = "PARTIALLY_VERIFIED", 0.6, "일부 출처만 뒷받침"
            else:
                status, conf, reason = "VERIFIED", 0.85, "복수 출처 일치"
            out.append(
                {
                    "fact": fact_text,
                    "status": status,
                    "confidence": conf,
                    "source_ids": c.get("source_ids", []),
                    "reason": reason,
                }
            )
        return {"facts": out}

    def _task_strategy(self, ctx: dict) -> dict:
        topic = ctx.get("topic", "the topic")
        goal = ctx.get("audience_goal", "BALANCED")
        return {
            "angle": f"'{topic}'를 '지금 당장 나에게 미치는 영향' 관점으로 재구성",
            "key_message": f"{topic}는 먼 미래가 아니라 이미 진행 중이며, 대응 시간은 있다.",
            "tone": "차분하지만 시급함이 느껴지는",
            "target_emotion": "각성 + 통제감",
            "talking_points": [
                f"{topic}의 현재 상태",
                "가장 먼저 영향을 받는 영역",
                "개인이 지금 할 수 있는 3가지",
                f"목표 지표: {goal}",
            ],
        }

    def _task_hook(self, ctx: dict) -> dict:
        topic = ctx.get("topic", "the topic")
        return {
            "hooks": [
                {"text": f"{topic}, 당신이 생각하는 것보다 훨씬 가까이 왔습니다.", "style": "위협+호기심", "score": 0.82},
                {"text": f"3년 안에 사라질 수도 있는 것 — {topic}의 진짜 이야기.", "style": "숫자+긴장", "score": 0.78},
                {"text": f"모두가 {topic}를 말하지만, 아무도 이건 말하지 않습니다.", "style": "정보격차", "score": 0.75},
            ]
        }

    def _task_script(self, ctx: dict) -> dict:
        topic = ctx.get("topic", "the topic")
        hook = ctx.get("hook_text", f"{topic} 이야기")
        facts = ctx.get("usable_fact_texts", [])
        lines = [
            hook,
            "",
            "먼저 사실부터 짚겠습니다.",
        ]
        for f in facts[:5]:
            lines.append(f"- {f}")
        lines += [
            "",
            "이게 왜 지금 중요하냐면, 변화는 이미 시작됐기 때문입니다.",
            "하지만 좋은 소식도 있습니다. 대응할 시간은 아직 있습니다.",
            "오늘 할 수 있는 건 세 가지입니다: 관찰하고, 배우고, 한 가지를 바꾸는 것.",
            "",
            "구독하고 다음 편에서 구체적인 방법을 확인하세요.",
        ]
        body = "\n".join(lines)
        return {"body": body, "word_count": len(body.split())}

    def _task_script_qa(self, ctx: dict) -> dict:
        body = ctx.get("script_body", "")
        unusable = ctx.get("unusable_fact_texts", [])
        used_bad = any(u and u in body for u in unusable)
        issues = []
        if used_bad:
            issues.append("미검증/반박된 사실이 스크립트에 포함됨")
        if len(body.split()) < 40:
            issues.append("스크립트가 너무 짧음")
        return {
            "passed": not issues,
            "issues": issues,
            "used_unverified_fact": used_bad,
        }

    # --- Phase 1-B media tasks --------------------------------------------

    def _task_platform_adapt(self, ctx: dict) -> dict:
        platform = ctx.get("platform", "generic")
        topic = ctx.get("topic", "주제")
        km = ctx.get("key_message", "")
        master_hook = ctx.get("master_hook", topic)
        facts = ctx.get("usable_fact_texts", [])
        dur = ctx.get("target_duration_s")
        family = ctx.get("family", "VIDEO")

        short = family in ("VIDEO",) and (dur or 999) <= 60
        hook = (
            f"{master_hook}" if not short
            else f"{topic}, 3초 안에 핵심만."
        )
        body_lines = [hook, ""]
        for f in facts[:3 if short else 5]:
            body_lines.append(f"- {f}")
        body_lines += ["", km or f"{topic}의 핵심은 지금 대응이 가능하다는 점입니다."]
        cta_map = {
            "threads": ("question", "당신 일에선 뭐가 먼저 바뀔까요?"),
            "x": ("question", "먼저 바뀔 직군, 뭐라고 보세요?"),
            "linkedin": ("comparison", "2년 전과 지금을 비교하면 방향은 분명합니다."),
            "naver_blog": ("save", "필요할 때 다시 볼 수 있게 저장해두세요."),
        }
        cta_type, cta = cta_map.get(platform, ("follow", "이어지는 편도 확인하세요."))
        return {
            "hook": hook,
            "script": "\n".join(body_lines),
            "cta": cta,
            "cta_type": cta_type,
            "title": f"{topic}" if not short else f"{topic} #shorts",
            "caption": f"{km[:80]}" if km else topic,
            "hashtags": [f"#{topic.split()[0]}", "#AI", "#커리어"][: 3 if short else 5],
            "notes": f"mock adaptation for {platform}",
        }

    def _task_scene_plan(self, ctx: dict) -> dict:
        import re

        script = ctx.get("script", "")
        target = float(ctx.get("scene_target_seconds", 4.5))
        fact_texts = ctx.get("usable_fact_texts", [])
        fact_ids = ctx.get("fact_source_ids", {})  # {fact_text: [ids]}
        num_re = re.compile(r"\d[\d,.%]*")

        raw = [s.strip(" -•\t") for s in re.split(r"(?<=[.!?。])\s+|\n+", script) if s.strip(" -•\t")]
        raw = [s for s in raw if len(s) > 1][:12] or [script[:120] or "장면"]
        scenes = []
        for i, line in enumerate(raw):
            wc = max(1, len(line.split()))
            dur = round(min(8.0, max(1.6, wc / 2.6 + (0.6 if i % 3 == 0 else -0.3) + (target - 4.5))), 2)
            has_num = bool(num_re.search(line))
            src_ids: list[str] = []
            if has_num:
                for ft in fact_texts:
                    if num_re.search(ft):
                        src_ids = fact_ids.get(ft, [])
                        break
            scenes.append({
                "narration": line,
                "estimated_duration": dur,
                "visual_description": f"{line[:60]} 를 표현하는 배경",
                "visual_prompt": {
                    "subject": line[:40],
                    "environment": "미니멀한 편집 스튜디오 톤",
                    "action": "정적",
                    "composition": "여백 있는 구도, 하단 자막 공간 확보",
                    "camera": "고정",
                    "lighting": "부드러운 확산광",
                    "style": "다큐멘터리풍, 과하지 않게",
                    "mood": "차분함",
                    "background": "저채도 그라디언트",
                    "text_safe_area": "하단 22%",
                    "negative_prompt": "글자, 워터마크, 로고, 왜곡된 손",
                },
                "source_ids": src_ids,
                "highlight_words": num_re.findall(line)[:2],
                "sound_effect": "whoosh" if i == 0 else ("ding" if has_num else ""),
                "music_energy": "high" if i == 0 else ("mid" if i < len(raw) - 1 else "low"),
            })
        return {"scenes": scenes}

    def _task_edit_decision(self, ctx: dict) -> dict:
        edits = []
        for s in ctx.get("scenes", []):
            energy = s.get("music_energy", "mid")
            edits.append({
                "scene_id": s.get("scene_id"),
                "scene_order": s.get("scene_order", 0),
                "clip_start": 0.0,
                "clip_end": float(s.get("estimated_duration", 4.0)),
                "speed": 1.0,
                "zoom": 1.08,
                "transition": "CUT",
                "subtitle_style": ctx.get("subtitle_style", "CLEAN"),
                "music_volume": {"low": 0.20, "mid": 0.16, "high": 0.12}.get(energy, 0.16),
                "voice_volume": 1.0,
                "sfx": [s["sound_effect"]] if s.get("sound_effect") else [],
            })
        return {"edits": edits}

    # --- Phase 4 autopilot tasks ---------------------------------------

    def _task_topic_extract(self, ctx: dict) -> dict:
        raw = ctx.get("raw_topic", "주제")
        cluster = ctx.get("cluster_hint") or ""
        audience = ctx.get("audience_hint", "일반 대중 / 커리어 관심층")
        base = raw.split(" — ")[-1].strip()
        cands = [
            {"topic": base, "angle": "구체 사례와 데이터로 '지금 나에게 미치는 영향'을 설명",
             "audience": audience, "intent": "informational", "freshness": "current"},
            {"topic": f"{base} — 실전 체크리스트",
             "angle": "오늘 바로 적용할 수 있는 단계별 행동으로 재구성",
             "audience": audience, "intent": "practical", "freshness": "evergreen"},
        ]
        return {"candidates": cands, "cluster_hint": cluster}

    def _task_originality(self, ctx: dict) -> dict:
        topic = ctx.get("topic", "")
        angle = ctx.get("angle", "")
        comp = ctx.get("competition_hint", "mid")
        score = 55.0
        if comp == "low":
            score += 22
        elif comp == "high":
            score -= 15
        if any(k in angle for k in ("데이터", "체크리스트", "사례", "비교", "단계")):
            score += 12
        if any(k in topic for k in ("순위", "총정리")):
            score -= 8
        score = max(0.0, min(100.0, score))
        return {
            "originality_score": round(score, 1),
            "overused_angles": ["단순 나열", "뻔한 결론 요약"],
            "missing_angles": ["특정 직군 맞춤 관점", "실제 수치 기반 비교", "반론과 한계 언급"],
        }
