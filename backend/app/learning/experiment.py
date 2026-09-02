from __future__ import annotations

import random
import statistics
from datetime import datetime, timezone

from app.config import get_settings
from app.db.models import Experiment, ExperimentResult

EXPERIMENT_VARIABLES = ["HOOK", "TITLE", "THUMBNAIL", "DURATION", "VOICE", "SUBTITLE",
                        "VISUAL_STYLE", "CTA", "PUBLISH_TIME", "NATURALNESS_PROFILE"]


def create_experiment(session, *, hypothesis: str, platform: str, content_type: str,
                      variable: str, control: dict, variant: dict,
                      primary_metric: str = "performance_score",
                      minimum_sample: int = 10) -> Experiment:
    assert variable in EXPERIMENT_VARIABLES, variable
    exp = Experiment(
        hypothesis=hypothesis, platform=platform, content_type=content_type,
        variable=variable, control=control, variant=variant,
        primary_metric=primary_metric, minimum_sample=minimum_sample,
        design="SEQUENTIAL_EXPERIMENT", status="RUNNING",
    )
    session.add(exp)
    session.flush()
    return exp


def record_result(session, experiment_id: str, arm: str, content_id: str,
                  metric_value: float | None) -> ExperimentResult:
    assert arm in ("control", "variant")
    r = ExperimentResult(experiment_id=experiment_id, arm=arm, content_id=content_id,
                         metric_value=metric_value)
    session.add(r)
    session.flush()
    return r


def evaluate(session, experiment_id: str) -> dict:
    exp = session.get(Experiment, experiment_id)
    if exp is None:
        raise ValueError("experiment not found")
    rows = session.query(ExperimentResult).filter_by(experiment_id=experiment_id).all()
    ctrl = [r.metric_value for r in rows if r.arm == "control" and r.metric_value is not None]
    var = [r.metric_value for r in rows if r.arm == "variant" and r.metric_value is not None]
    result = {"n_control": len(ctrl), "n_variant": len(var)}
    if len(ctrl) < exp.minimum_sample or len(var) < exp.minimum_sample:
        result["status"] = "INSUFFICIENT_SAMPLE"
        exp.result = result
        session.flush()
        return result

    mc, mv = statistics.fmean(ctrl), statistics.fmean(var)
    pooled_sd = statistics.pstdev(ctrl + var) or 1.0
    effect = (mv - mc) / pooled_sd            # Cohen's d-ish
    lift = round((mv / mc - 1.0), 3) if mc else 0.0
    # rough confidence from effect size + sample (NOT a real p-value; SEQUENTIAL)
    conf = round(min(0.95, 0.4 + abs(effect) * 0.5 + 0.01 * min(len(ctrl), len(var))), 3)
    winner = "variant" if mv > mc else "control"
    result.update({"status": "COMPLETED", "mean_control": round(mc, 2), "mean_variant": round(mv, 2),
                   "lift": lift, "effect_size": round(effect, 3), "winner": winner,
                   "note": "SEQUENTIAL_EXPERIMENT — not a randomised A/B; treat as directional"})
    exp.result = result
    exp.confidence = conf
    exp.status = "COMPLETED"
    exp.end_at = datetime.now(timezone.utc)
    session.flush()
    return result


def evaluate_all(session) -> int:
    n = 0
    for exp in session.query(Experiment).filter_by(status="RUNNING").all():
        r = evaluate(session, exp.id)
        if r.get("status") == "COMPLETED":
            n += 1
    return n


def should_explore(seed: str | None = None) -> bool:
    """80/20 exploit/explore by default (configurable). Never permanently excludes
    a new option."""
    ratio = get_settings().exploration_ratio
    rng = random.Random(seed) if seed else random
    return rng.random() < ratio
