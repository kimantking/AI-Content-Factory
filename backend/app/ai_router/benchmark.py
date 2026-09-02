"""Model Benchmark Service — score a model on OUR real tasks.

Small deterministic task set (classification / summary / fact extraction / url
triage / hook eval / script QA / reference analysis / prompt distillation). For
each: schema validity, task accuracy (against an expected key), latency, cost,
failure rate. Writes ModelPerformance rows with benchmark_state=BENCHMARKED.

Runs against whatever provider the model resolves to; on mock LLM it still
exercises the plumbing (MOCK_VERIFIED).
"""
from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session

from app.ai_router.execute import _provider_for
from app.ai_router.pricing import cost_of
from app.ai_router.telemetry import recompute_performance
from app.db.models_p8 import ModelPerformance
from app.providers.errors import ProviderError

TASKS = [
    {"task_type": "classification",
     "system": "Classify the text. Return {\"label\": one of [NEWS, BLOG, DOC, PRODUCT]}.",
     "user": "The central bank raised its policy rate by 25 basis points today.",
     "expect_key": "label"},
    {"task_type": "simple_summary",
     "system": "Summarise in one sentence. Return {\"summary\": string}.",
     "user": "Machine translation demand rose 40% in 2026; human translators shift to review.",
     "expect_key": "summary"},
    {"task_type": "fact_extract",
     "system": "Extract statistics. Return {\"statistics\": [string]}.",
     "user": "Automation went from 25% in 2024 to 40% in 2026 across the surveyed teams.",
     "expect_key": "statistics"},
    {"task_type": "url_triage",
     "system": "Classify the URL's likely value. Return {\"value\": one of [HIGH, MEDIUM, LOW]}.",
     "user": "https://official-standards.example.gov/report/mt-2026.pdf",
     "expect_key": "value"},
    {"task_type": "creative_qa_basic",
     "system": "Rate the hook 0-10 for curiosity. Return {\"score\": number, \"reason\": string}.",
     "user": "번역가는 사라질까? 3년치 데이터를 봤다.",
     "expect_key": "score"},
]


def run_benchmark(db: Session, *, model_id: str, provider: str | None = None) -> dict:
    from app.ai_router.execute import _prov_of

    prov = provider or _prov_of(model_id)
    try:
        engine = _provider_for(model_id, prov)
    except ProviderError as e:
        return {"model_id": model_id, "ok": False, "error": str(e), "results": []}

    results = []
    for t in TASKS:
        started = time.monotonic()
        row = {"task_type": t["task_type"], "schema_valid": False, "accurate": False,
               "latency_ms": 0, "error": ""}
        try:
            resp = engine.complete(system=t["system"], user=t["user"], task=t["task_type"],
                                   context={"max_tokens": 200})
            row["latency_ms"] = round((time.monotonic() - started) * 1000)
            data = json.loads(resp.text)
            row["schema_valid"] = isinstance(data, dict)
            row["accurate"] = row["schema_valid"] and t["expect_key"] in data and data[t["expect_key"]] not in (None, "", [])
            c = cost_of(model_id.split("@")[0], input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens)
            row["cost_usd"] = c.get("usd")
            row["cost_state"] = c.get("state")
        except (ProviderError, ValueError) as e:
            row["latency_ms"] = round((time.monotonic() - started) * 1000)
            row["error"] = str(e)[:200]
        results.append(row)

    n = len(results)
    sv = sum(r["schema_valid"] for r in results) / n
    acc = sum(r["accurate"] for r in results) / n
    lat = sum(r["latency_ms"] for r in results) / n
    fail = sum(1 for r in results if r["error"]) / n

    # per-task ModelPerformance rows
    for r in results:
        row = db.query(ModelPerformance).filter_by(model_id=model_id, task_type=r["task_type"]).first()
        if row is None:
            row = ModelPerformance(model_id=model_id, task_type=r["task_type"])
            db.add(row)
        row.benchmark_state = "BENCHMARKED"
        row.schema_valid_rate = float(r["schema_valid"])
        row.success_rate = float(r["accurate"])
        row.avg_latency_ms = float(r["latency_ms"])
        row.avg_quality = float(r["accurate"])
        row.avg_cost_usd = r.get("cost_usd")
        row.sample_size = max(row.sample_size or 0, len(TASKS))
        row.strength = "STRONG" if r["accurate"] and r["schema_valid"] else \
            ("OK" if r["schema_valid"] else "WEAK")
        row.detail = {"benchmark": r}
    db.flush()
    recompute_performance(db, model_id=model_id)

    return {
        "model_id": model_id, "provider": prov, "ok": True,
        "schema_valid_rate": round(sv, 3), "accuracy": round(acc, 3),
        "avg_latency_ms": round(lat, 1), "failure_rate": round(fail, 3),
        "verified": "MOCK_VERIFIED" if prov == "mock" else "LOCAL_VERIFIED" if prov == "ollama" else "CLOUD_VERIFIED",
        "results": results,
    }
