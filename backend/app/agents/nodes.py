from __future__ import annotations

import json

from app.agents import factcheck as _factcheck
from app.agents import hooks as _hooks
from app.agents import research as _research
from app.agents.common import (
    parse_json,
    replace_facts,
    replace_hooks,
    replace_sources,
    replace_strategy,
    set_step,
)
from app.agents.state import PipelineState
from app.config import get_settings
from app.db.base import session_scope
from app.db.models import Campaign, Script
from app.naturalness import load_voice_profile, natural_writing_pass, score_ai_slop
from app.naturalness.cta import pick_cta
from app.providers.errors import InsufficientResearchError
from app.providers.registry import get_search_provider
# LLM access goes through app.agents.model_gateway (AUDIT-P8-001) — no direct LLM provider here
from app.providers.retry import call_with_retry
from app.services.agent_logger import agent_run
from app.services.budget import check_budget
from app.services.cost import llm_cost, log_cost, search_cost
from app.services.prompts import load_prompt, register_prompt

_PROMPT_TASKS = ["research", "fact_checker", "strategy", "hook", "script", "script_qa"]

# Deterministic query-angle variation for the research fix pass. Instead of always
# re-searching the same string, each fix round targets a different evidence angle
# (statistics -> counter-evidence -> primary/recent sources). Pattern from
# gpt-researcher / STORM (query decomposition); kept to ONE query per pass so
# search-call count and cost are unchanged.
_FIX_QUERY_ANGLES = [
    "{topic} 통계 데이터 최신 수치",
    "{topic} 반대 근거 비판 한계",
    "{topic} 1차 출처 공식 발표 최근",
]


def _fix_query(topic: str, fix_round: int) -> str:
    angle = _FIX_QUERY_ANGLES[(fix_round - 1) % len(_FIX_QUERY_ANGLES)]
    return angle.format(topic=topic)


def _run_llm(session, handle, *, campaign_id, agent_name, prompt_name, task, context):
    """Every Phase 1-A agent LLM call goes through the Model Execution Gateway
    (AUDIT-P8-001): task -> ModelRouter -> local Ollama / cheap / premium /
    escalation / telemetry. No direct provider call here."""
    from app.agents.model_gateway import routed_complete

    prompt = load_prompt(prompt_name)
    check_budget(session, campaign_id)
    camp = session.get(Campaign, campaign_id)
    wid = camp.workspace_id if camp else None

    resp = call_with_retry(
        lambda: routed_complete(
            agent_name=agent_name, task=task,
            system=prompt.body,
            user=json.dumps(context, ensure_ascii=False),
            context=context, session=session, campaign_id=campaign_id, workspace_id=wid,
        ),
        on_retry=lambda i, e: setattr(handle, "_extra", {**handle._extra, "retries": i}),
    )
    cost = llm_cost(resp.provider, resp.model, resp.input_tokens, resp.output_tokens)
    log_cost(
        session, campaign_id=campaign_id, agent_name=agent_name, kind="LLM",
        provider=resp.provider, model=resp.model,
        input_tokens=resp.input_tokens, output_tokens=resp.output_tokens, amount_usd=cost,
    )
    handle.record_usage(
        input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
        estimated_cost=cost, provider=resp.provider, model=resp.model,
    )
    if getattr(handle, "_extra", None) is not None:
        handle._extra = {**handle._extra, "routing_tier": resp.tier,
                         "routing_reason": resp.routing_reason,
                         "routing_fallback": resp.fallback_used, "routed": resp.routed}
    return parse_json(resp.text, task=task)


# --------------------------------------------------------------------------- #
# nodes
# --------------------------------------------------------------------------- #

def create_campaign_node(state: PipelineState) -> dict:
    cid = state["campaign_id"]
    with session_scope() as session:
        camp = session.get(Campaign, cid)
        if camp is None:
            raise ValueError(f"campaign {cid} not found")
        camp.status = "RUNNING"
        camp.current_step = "create_campaign"
        for name in _PROMPT_TASKS:
            register_prompt(session, name)
    return {"status": "RUNNING", "research_fix_count": 0}


def _do_research(state: PipelineState, *, fix: bool) -> dict:
    s = get_settings()
    cid = state["campaign_id"]
    topic = state["topic"]
    fix_count = int(state.get("research_fix_count", 0)) + (1 if fix else 0)
    agent_name = "Research Agent"
    step = "research_fix" if fix else "research"

    with session_scope() as session:
        set_step(session, cid, step)
        with agent_run(campaign_id=cid, agent_name=agent_name, prompt_version="v1") as handle:
            search = get_search_provider()
            prev_keywords = list((state.get("knowledge_pack", {}) or {}).get("keywords", []))
            if fix:
                queries = [_fix_query(topic, fix_count)]     # one targeted angle per fix pass
            else:
                # First pass: decompose the topic into complementary sub-queries
                # (gpt-researcher / STORM pattern), run them, then merge + rank by
                # domain authority / topical match / freshness + domain diversity.
                queries = _research.expand_queries(topic, prev_keywords, limit=3)
            groups = []
            for q in queries:
                groups.append(call_with_retry(lambda q=q: search.search(q, max_results=6)))
                scost = search_cost(search.name)
                log_cost(session, campaign_id=cid, agent_name=agent_name, kind="SEARCH",
                         provider=search.name, amount_usd=scost)
                handle.record_usage(estimated_cost=scost)
            ranked = _research.merge_and_rank(groups, topic=topic, limit=8)
            if len(ranked) < 2:
                raise InsufficientResearchError(f"only {len(ranked)} sources for '{topic}'")
            handle._extra = {**handle._extra,
                             "sub_queries": len(queries),
                             "source_diversity": _research.source_diversity(ranked)}

            sources = replace_sources(session, cid, ranked)

            data = _run_llm(
                session, handle, campaign_id=cid, agent_name=agent_name,
                prompt_name="research", task="research",
                context={
                    "topic": topic,
                    "sources": [{"id": s_["id"], "title": s_["title"], "snippet": s_["snippet"],
                                 "url": s_["url"], "published_at": s_["published_at"]} for s_ in sources],
                    "research_fix_count": fix_count,
                    "audience_goal_hint": state.get("audience_goal", "BALANCED"),
                },
            )

    candidate_facts = data.get("candidate_facts", [])
    contradictions = _research.find_contradictions(candidate_facts)
    kp = {
        "topic": topic,
        "audience": data.get("audience", ""),
        "verified_facts": [],
        "statistics": data.get("statistics", []),
        "examples": data.get("examples", []),
        "sources": sources,
        "counter_arguments": data.get("counter_arguments", []),
        "interesting_points": data.get("interesting_points", []),
        "visual_opportunities": data.get("visual_opportunities", []),
        "keywords": data.get("keywords", []),
        "risk_flags": data.get("risk_flags", []),
        "contradictions": contradictions,
        "source_diversity": _research.source_diversity(sources),
        "coverage_score": _research.coverage_score(candidate_facts, sources),
    }
    return {
        "sources": sources,
        "candidate_facts": candidate_facts,
        "knowledge_pack": kp,
        "research_fix_count": fix_count,
    }


def research_node(state: PipelineState) -> dict:
    return _do_research(state, fix=False)


def research_fix_node(state: PipelineState) -> dict:
    return _do_research(state, fix=True)


def fact_check_node(state: PipelineState) -> dict:
    cid = state["campaign_id"]
    sources = state.get("sources", [])
    # Atomic claim extraction + check-worthiness filter (Loki/SAFE pattern).
    # A compound claim is split into independently checkable parts; a fact with
    # no clause boundary (every mock fact) passes through unchanged.
    atomic = _factcheck.atomic_claims(state.get("candidate_facts", []))
    checkable = [c for c in atomic if _factcheck.checkworthy(c.get("fact", ""))] or atomic
    with session_scope() as session:
        set_step(session, cid, "fact_check")
        with agent_run(campaign_id=cid, agent_name="Fact Checker", prompt_version="v1") as handle:
            data = _run_llm(
                session, handle, campaign_id=cid, agent_name="Fact Checker",
                prompt_name="fact_checker", task="fact_check",
                context={
                    "topic": state["topic"],
                    "candidate_facts": checkable,
                    "sources": [{"id": s["id"], "title": s["title"], "snippet": s["snippet"]}
                                for s in sources],
                },
            )
            # Post-process: cross-source agreement count, temporal markers,
            # re-blended confidence, lone-source VERIFIED -> PARTIALLY_VERIFIED.
            facts = _factcheck.enrich_facts(data.get("facts", []), sources)
            replace_facts(session, cid, facts)

    total = len(facts) or 1
    usable = [f for f in facts if f.get("status") in ("VERIFIED", "PARTIALLY_VERIFIED")]
    score = round(len(usable) / total, 3)
    kp = dict(state.get("knowledge_pack", {}))
    kp["verified_facts"] = facts
    with session_scope() as session:
        camp = session.get(Campaign, cid)
        if camp:
            camp.fact_score = score
    return {"facts": facts, "fact_score": score, "knowledge_pack": kp}


def fact_score_router(state: PipelineState) -> str:
    s = get_settings()
    score = float(state.get("fact_score", 0.0))
    fixes = int(state.get("research_fix_count", 0))
    if score < s.fact_score_threshold and fixes < s.research_fix_max:
        return "research_fix"
    return "strategize"


def strategy_node(state: PipelineState) -> dict:
    cid = state["campaign_id"]
    kp = state.get("knowledge_pack", {})
    usable_texts = [f["fact"] for f in state.get("facts", [])
                    if f.get("status") in ("VERIFIED", "PARTIALLY_VERIFIED")]

    # Phase 3: retrieve relevant learning memories as STRATEGIC GUIDANCE (never facts)
    memory_ctx = {"enabled": False, "items": [], "text": ""}
    try:
        from app.learning.injection import strategy_memory_context

        with session_scope() as session:
            memory_ctx = strategy_memory_context(
                session, topic=state["topic"],
                platforms=state.get("platforms", []),
                objective=state.get("audience_goal", "BALANCED"),
            )
    except Exception:  # noqa: BLE001 — learning is advisory; never block strategy
        memory_ctx = {"enabled": False, "items": [], "text": ""}

    with session_scope() as session:
        set_step(session, cid, "strategize")
        with agent_run(campaign_id=cid, agent_name="Content Strategist", prompt_version="v1") as handle:
            data = _run_llm(
                session, handle, campaign_id=cid, agent_name="Content Strategist",
                prompt_name="strategy", task="strategy",
                context={
                    "topic": state["topic"],
                    "audience": kp.get("audience", ""),
                    "audience_goal": state.get("audience_goal", "BALANCED"),
                    "usable_fact_texts": usable_texts,
                    "counter_arguments": kp.get("counter_arguments", []),
                    "interesting_points": kp.get("interesting_points", []),
                    "keywords": kp.get("keywords", []),
                    "strategic_guidance": memory_ctx.get("text", ""),
                    "memory_items": memory_ctx.get("items", []),
                },
            )
            data["_memory_context"] = memory_ctx
            replace_strategy(session, cid, data)
    return {"strategy": data}


def hook_node(state: PipelineState) -> dict:
    cid = state["campaign_id"]
    strat = state.get("strategy", {})
    with session_scope() as session:
        set_step(session, cid, "hook")
        with agent_run(campaign_id=cid, agent_name="Hook Agent", prompt_version="v1") as handle:
            data = _run_llm(
                session, handle, campaign_id=cid, agent_name="Hook Agent",
                prompt_name="hook", task="hook",
                context={
                    "topic": state["topic"],
                    "angle": strat.get("angle", ""),
                    "key_message": strat.get("key_message", ""),
                    "target_emotion": strat.get("target_emotion", ""),
                    "talking_points": strat.get("talking_points", []),
                },
            )
            raw_hooks = data.get("hooks", [])
            # recent hooks (other campaigns) for a similarity penalty
            from app.db.models import Hook as _Hook

            recent = [r[0] for r in session.query(_Hook.text)
                      .filter(_Hook.campaign_id != cid)
                      .order_by(_Hook.id.desc()).limit(12).all()]
            usable_texts = [f["fact"] for f in state.get("facts", [])
                            if f.get("status") in ("VERIFIED", "PARTIALLY_VERIFIED")]
            platform = (state.get("platforms") or [None])[0]
            hooks, hook_meta = _hooks.refine(
                raw_hooks, platform=platform, recent_hook_texts=recent,
                usable_fact_texts=usable_texts,
            )
            # persist ranked by the adjusted score
            replace_hooks(session, cid, [{**h, "score": h.get("adjusted_score", h.get("score", 0))}
                                         for h in hooks])
            handle._extra = {**handle._extra, "hook_diversity": hook_meta.get("after_diversity"),
                             "hook_exaggeration": hook_meta.get("any_exaggeration")}
    chosen = hooks[0] if hooks else {"text": state["topic"], "style": "", "score": 0}
    return {"hooks": hooks, "chosen_hook": chosen}


def script_node(state: PipelineState) -> dict:
    """Draft Script -> Natural Writing Pass -> Fact Preservation Check (Amendment §4)."""
    s = get_settings()
    cid = state["campaign_id"]
    strat = state.get("strategy", {})
    facts = state.get("facts", [])
    usable_texts = [f["fact"] for f in facts if f.get("status") in ("VERIFIED", "PARTIALLY_VERIFIED")]
    unusable_texts = [f["fact"] for f in facts if f.get("status") in ("UNVERIFIED", "CONTRADICTED")]
    chosen_hook = state.get("chosen_hook", {})

    # rotating CTA (Amendment §33)
    from app.db.models import Script as ScriptModel_

    with session_scope() as session:
        recent = [
            r[0] for r in session.query(ScriptModel_.cta_type)
            .filter(ScriptModel_.cta_type.isnot(None))
            .order_by(ScriptModel_.id.desc()).limit(5).all()
        ]
    cta_type, cta_text = pick_cta(seed=cid, recent_types=recent)

    with session_scope() as session:
        set_step(session, cid, "write_script")
        with agent_run(campaign_id=cid, agent_name="Script Agent", prompt_version="v1") as handle:
            draft = _run_llm(
                session, handle, campaign_id=cid, agent_name="Script Agent",
                prompt_name="script", task="script",
                context={
                    "topic": state["topic"],
                    "angle": strat.get("angle", ""),
                    "key_message": strat.get("key_message", ""),
                    "tone": strat.get("tone", ""),
                    "hook_text": chosen_hook.get("text", ""),
                    "usable_fact_texts": usable_texts,
                    "talking_points": strat.get("talking_points", []),
                    "cta_text": cta_text,
                },
            )
    draft_body = draft.get("body", "")
    if cta_text and cta_text not in draft_body:
        draft_body = draft_body.rstrip() + "\n\n" + cta_text

    # Natural Writing Pass
    nat_notes: list[str] = []
    body = draft_body
    slop_after = score_ai_slop(draft_body, max_target=s.max_ai_slop_score)
    slop_before = slop_after
    if s.natural_writing_enabled:
        voice = load_voice_profile(s.default_brand)
        # natural-writing rewrite also goes through the gateway (routed as a
        # 'rewrite' / standard task). MOCK MODE keeps the deterministic pass.
        from app.agents.model_gateway import GatewayLLM

        llm_for_nat = None if s.llm_is_mock else GatewayLLM(
            agent_name="Script Agent", session=session, campaign_id=cid)
        result = natural_writing_pass(
            draft_body, voice=voice,
            usable_facts=usable_texts, unusable_facts=unusable_texts,
            llm=llm_for_nat, max_target=s.max_ai_slop_score,
        )
        body = result.text
        slop_before = result.slop_before
        slop_after = result.slop_after
        nat_notes = result.notes + ([] if result.fact_preserved else ["FACT_PRESERVATION_FAILED"])

    return {
        "script": {
            "platform": "MASTER",
            "draft_body": draft_body,
            "body": body,
            "word_count": len(body.split()),
            "cta_type": cta_type,
            "ai_slop_score": slop_after.score,
            "naturalness": {
                "ai_slop_before": slop_before.score,
                "ai_slop_after": slop_after.score,
                "burstiness": slop_after.burstiness,
                "breakdown": slop_after.breakdown,
                "tells": slop_after.tells,
                "notes": nat_notes,
                "max_target": s.max_ai_slop_score,
            },
        }
    }


def script_qa_node(state: PipelineState) -> dict:
    s = get_settings()
    cid = state["campaign_id"]
    script = state.get("script", {})
    facts = state.get("facts", [])
    usable_texts = [f["fact"] for f in facts if f.get("status") in ("VERIFIED", "PARTIALLY_VERIFIED")]
    unusable_texts = [f["fact"] for f in facts if f.get("status") in ("UNVERIFIED", "CONTRADICTED")]
    strat = state.get("strategy", {})

    with session_scope() as session:
        set_step(session, cid, "qa_script")
        with agent_run(campaign_id=cid, agent_name="Script QA", prompt_version="v1") as handle:
            data = _run_llm(
                session, handle, campaign_id=cid, agent_name="Script QA",
                prompt_name="script_qa", task="script_qa",
                context={
                    "script_body": script.get("body", ""),
                    "usable_fact_texts": usable_texts,
                    "unusable_fact_texts": unusable_texts,
                    "key_message": strat.get("key_message", ""),
                },
            )

    slop = float(script.get("ai_slop_score") or 0.0)
    slop_ok = slop <= s.max_ai_slop_score
    issues = list(data.get("issues", []))
    if not slop_ok:
        issues.append(f"AI_SLOP_SCORE {slop} > 목표 {s.max_ai_slop_score}")
    # A QA model that returns valid JSON without an explicit `passed` flag (e.g. a
    # small local model routed here for a light task) must NOT hard-fail the whole
    # campaign on this SOFT gate — Governance is the hard gate downstream. Only an
    # explicit `passed: false` (or a real issue / unverified-fact / slop breach) fails.
    qa_flag = data.get("passed")
    qa_ok = True if qa_flag is None else bool(qa_flag)
    passed = qa_ok and not data.get("used_unverified_fact") and slop_ok and not issues
    report = {
        "passed": passed,
        "issues": issues,
        "used_unverified_fact": bool(data.get("used_unverified_fact")),
        "ai_slop_score": slop,
        "ai_slop_ok": slop_ok,
    }
    return {"script_qa": report}


def persist_node(state: PipelineState) -> dict:
    cid = state["campaign_id"]
    script = state.get("script", {})
    qa = state.get("script_qa", {})
    kp = state.get("knowledge_pack", {})
    passed = bool(qa.get("passed"))

    with session_scope() as session:
        camp = session.get(Campaign, cid)
        session.query(Script).filter_by(campaign_id=cid).delete()
        session.flush()
        session.add(Script(
            campaign_id=cid,
            platform=script.get("platform", "MASTER"),
            body=script.get("body", ""),
            draft_body=script.get("draft_body"),
            word_count=int(script.get("word_count", 0)),
            qa_passed=passed,
            qa_report=qa,
            cta_type=script.get("cta_type"),
            ai_slop_score=script.get("ai_slop_score"),
            naturalness=script.get("naturalness", {}),
        ))
        if camp:
            camp.knowledge_pack = kp
            camp.current_step = "done"
            camp.status = "SUCCESS" if passed else "FAILED"
            if not passed:
                camp.error_message = "; ".join(qa.get("issues", [])) or "script QA failed"
    return {"status": "SUCCESS" if passed else "FAILED"}
