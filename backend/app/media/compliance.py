from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(r"\d[\d,.%]+")


@dataclass
class ComplianceReport:
    verdict: str                       # PASS | FIX_REQUIRED | BLOCK
    findings: list[str] = field(default_factory=list)
    fix_scenes: list[int] = field(default_factory=list)


def check(*, scenes: list[dict], assets: list[dict], usable_fact_texts: list[str],
          screen_texts: list[str]) -> ComplianceReport:
    findings: list[str] = []
    fix_scenes: list[int] = []
    block = False

    fact_blob = " ".join(usable_fact_texts)
    fact_nums = set(_NUM.findall(fact_blob))

    # 1. statistics on screen / narration with no verified source
    for i, s in enumerate(scenes):
        text = f"{s.get('narration', '')} {s.get('subtitle_text', '')}"
        for n in _NUM.findall(text):
            if n not in fact_nums:
                findings.append(f"scene {i + 1}: unsupported statistic {n!r}")
                fix_scenes.append(i + 1)
        if s.get("visual_type") == "CHART" and not s.get("source_ids"):
            findings.append(f"scene {i + 1}: chart without source_ids")
            fix_scenes.append(i + 1)

    # 2. asset licence / provenance
    for a in assets:
        meta = a.get("meta") or {}
        if a.get("asset_type") in {"music", "bgm"}:
            if not meta.get("commercial_use_allowed", False):
                findings.append(f"music asset {a.get('id')}: commercial use not confirmed")
                block = True
            if meta.get("license_type") in (None, "", "unknown"):
                findings.append(f"music asset {a.get('id')}: license unknown")
                block = True
        if a.get("provider_mode") == "ERROR":
            findings.append(f"asset {a.get('id')}: provider errored")

    # 3. duplicated scene visuals (exact prompt repeats back-to-back)
    prompts = [str(s.get("visual_prompt")) for s in scenes]
    for i in range(1, len(prompts)):
        if prompts[i] and prompts[i] == prompts[i - 1]:
            findings.append(f"scene {i + 1}: identical visual to previous scene")
            fix_scenes.append(i + 1)

    # 4. broken screen text (empty or placeholder tokens leaking through)
    for t in screen_texts:
        if re.search(r"\{\{|\}\}|TODO|lorem ipsum", t, re.I):
            findings.append(f"screen text contains placeholder: {t[:40]!r}")
            block = True

    if block:
        verdict = "BLOCK"
    elif fix_scenes or findings:
        verdict = "FIX_REQUIRED"
    else:
        verdict = "PASS"
    return ComplianceReport(verdict=verdict, findings=findings, fix_scenes=sorted(set(fix_scenes)))
