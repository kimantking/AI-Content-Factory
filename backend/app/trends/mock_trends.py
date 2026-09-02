from __future__ import annotations

import hashlib

from app.trends.base import RawTrend

# Deterministic offline trend catalogue. Rich enough to exercise velocity,
# acceleration, freshness, dedup/cluster, competition, risk, fatigue and cost.
# A mock trend is never reported as a real source hit (provider_mode=MOCK).

# (raw_topic, cluster_hint, shape, risk_hint, competition_hint, evergreen)
#   shape: breakout | rising | stable | declining | evergreen
_CATALOG: list[tuple[str, str, str, str, str, bool]] = [
    ("AI로 사라질 가능성이 높은 직업", "ai-job", "rising", "LOW", "high", False),
    ("인공지능이 대체할 일자리 전망", "ai-job", "rising", "LOW", "high", False),
    ("AI 때문에 없어지는 직업 순위", "ai-job", "stable", "LOW", "high", False),
    ("2026년 직장인이 실제로 가장 많이 쓰는 AI 기능", "ai-tool", "breakout", "LOW", "mid", False),
    ("무료로 쓸 수 있는 업무 자동화 AI 도구", "ai-tool", "rising", "LOW", "mid", True),
    ("AI 에이전트로 반복 업무 자동화하는 법", "ai-tool", "rising", "LOW", "low", False),
    ("ChatGPT 대체 국산 AI 비교", "ai-tool", "declining", "LOW", "high", False),
    ("재택근무가 도시 부동산에 미치는 영향", "remote-realestate", "stable", "LOW", "mid", True),
    ("원격근무 기업이 사무실을 줄이는 이유", "remote-realestate", "declining", "LOW", "mid", False),
    ("주 4일제 도입 기업의 실제 생산성 데이터", "work-policy", "rising", "LOW", "low", False),
    ("신입 개발자 채용 시장이 얼어붙은 이유", "dev-jobs", "breakout", "LOW", "mid", False),
    ("비전공자 개발자 취업 현실 2026", "dev-jobs", "stable", "LOW", "high", False),
    ("30대 직장인 이직 타이밍 판단하는 법", "career", "evergreen", "LOW", "mid", True),
    ("퇴사 전에 반드시 준비해야 할 것", "career", "evergreen", "LOW", "high", True),
    ("직장인 부업으로 월 100만원 만드는 현실적인 방법", "side-income", "rising", "FINANCIAL", "high", True),
    ("초보자를 위한 ETF 적립식 투자", "investing", "stable", "FINANCIAL", "high", True),
    ("비트코인 반감기 이후 가격 시나리오", "crypto", "declining", "FINANCIAL", "high", False),
    ("가상자산 과세 유예 논란 정리", "crypto", "rising", "FINANCIAL", "mid", False),
    ("전세사기 피하는 계약서 체크리스트", "housing-safety", "stable", "LEGAL", "mid", True),
    ("청년 월세 지원 제도 총정리", "housing-policy", "stable", "LEGAL", "mid", True),
    ("다음 총선 주요 쟁점 미리보기", "election", "rising", "ELECTION", "high", False),
    ("대선 여론조사 해석할 때 흔한 착각", "election", "stable", "POLITICAL", "high", False),
    ("독감 예방접종 언제 맞아야 효과적일까", "health", "seasonal", "MEDICAL", "mid", True),
    ("혈압약 복용 중 흔한 오해", "health", "stable", "MEDICAL", "high", True),
    ("직장인 번아웃 초기 신호 7가지", "wellbeing", "evergreen", "LOW", "high", True),
    ("수면의 질을 높이는 저녁 루틴", "wellbeing", "evergreen", "LOW", "high", True),
    ("가성비 좋은 재택 홈오피스 셋업", "gear", "stable", "LOW", "mid", True),
    ("노트북 오래 쓰는 배터리 관리법", "gear", "evergreen", "LOW", "high", True),
    ("한국 관광객이 늘어난 저평가 여행지", "travel", "rising", "LOW", "mid", False),
    ("항공권 싸게 사는 시점 데이터 분석", "travel", "evergreen", "LOW", "high", True),
    ("혼자 사는 사람을 위한 10분 요리", "cooking", "evergreen", "LOW", "high", True),
    ("에어프라이어 200% 활용법", "cooking", "declining", "LOW", "high", True),
    ("생성형 AI 저작권 판결 최신 동향", "ai-legal", "breakout", "LEGAL", "low", False),
    ("AI가 만든 콘텐츠 표시 의무화 논의", "ai-legal", "rising", "LEGAL", "low", False),
    ("숏폼 알고리즘이 최근 바뀐 정황", "creator", "breakout", "LOW", "mid", False),
    ("조회수보다 저장률이 중요한 이유", "creator", "stable", "LOW", "mid", True),
    ("전기차 보조금 개편 요약", "ev-policy", "rising", "FINANCIAL", "mid", False),
    ("중고차 살 때 꼭 확인할 항목", "car", "evergreen", "LOW", "high", True),
    ("금리 인하가 대출자에게 미치는 실제 영향", "rates", "rising", "FINANCIAL", "high", False),
    ("연말정산 놓치기 쉬운 공제 항목", "tax", "seasonal", "FINANCIAL", "high", True),
    ("초보 러너를 위한 4주 프로그램", "fitness", "evergreen", "LOW", "high", True),
    ("사무직의 거북목 완화 스트레칭", "fitness", "evergreen", "LOW", "high", True),
    ("반려동물 보험 가입 전 비교 포인트", "pet", "stable", "FINANCIAL", "mid", True),
    ("층간소음 분쟁 대응 절차", "living", "stable", "LEGAL", "mid", True),
    ("전세 대출 갈아타기 조건 정리", "housing-finance", "rising", "FINANCIAL", "mid", False),
    ("AI 면접 대비하는 실전 팁", "job-hunt", "rising", "LOW", "mid", False),
    ("이력서에서 바로 탈락하는 표현", "job-hunt", "evergreen", "LOW", "high", True),
    ("주니어 PM이 자주 하는 실수", "pm", "stable", "LOW", "low", True),
    ("데이터 분석가 포트폴리오 구성법", "data-career", "stable", "LOW", "mid", True),
    ("영어 회화 혼자 연습하는 루틴", "study", "evergreen", "LOW", "high", True),
    ("자격증 없이 이직에 성공한 사례 분석", "career", "declining", "LOW", "mid", False),
    ("퇴직연금 디폴트옵션 선택 가이드", "retirement", "rising", "FINANCIAL", "mid", True),
    ("소상공인 지원금 신청 자격 정리", "smb-policy", "rising", "LEGAL", "mid", False),
    ("생성형 AI로 만든 이미지의 한계", "ai-visual", "stable", "LOW", "mid", True),
    ("영상 편집 자동화 툴 비교", "video-tools", "rising", "LOW", "mid", False),
    ("숏폼 첫 3초 이탈률 줄이는 법", "creator", "rising", "LOW", "mid", True),
    ("AI 음성 더빙 품질 어디까지 왔나", "ai-audio", "rising", "LOW", "low", False),
    ("직장 내 AI 사용 가이드라인 만드는 법", "ai-policy", "breakout", "LOW", "low", False),
    ("리모트 팀 커뮤니케이션 원칙", "remote-work", "evergreen", "LOW", "high", True),
    ("월급쟁이 절세 계좌 3종 비교", "tax", "stable", "FINANCIAL", "high", True),
]

_SHAPE_SERIES = {
    "breakout":  {"1h": 0.90, "6h": 0.85, "24h": 0.55, "3d": 0.30, "7d": 0.18, "30d": 0.10},
    "rising":    {"1h": 0.60, "6h": 0.55, "24h": 0.50, "3d": 0.40, "7d": 0.32, "30d": 0.22},
    "stable":    {"1h": 0.45, "6h": 0.46, "24h": 0.45, "3d": 0.44, "7d": 0.45, "30d": 0.43},
    "declining": {"1h": 0.20, "6h": 0.24, "24h": 0.32, "3d": 0.45, "7d": 0.62, "30d": 0.80},
    "evergreen": {"1h": 0.40, "6h": 0.40, "24h": 0.41, "3d": 0.40, "7d": 0.41, "30d": 0.40},
    "seasonal":  {"1h": 0.55, "6h": 0.53, "24h": 0.50, "3d": 0.42, "7d": 0.35, "30d": 0.28},
}


def _f(s: str) -> float:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def build_catalog(country: str = "KR", language: str = "ko") -> list[RawTrend]:
    out: list[RawTrend] = []
    for raw_topic, cluster, shape, risk, comp, evergreen in _CATALOG:
        j = _f(raw_topic)
        base = _SHAPE_SERIES.get(shape, _SHAPE_SERIES["stable"])
        series = {k: round(min(1.0, v * (0.85 + 0.3 * j)), 4) for k, v in base.items()}
        out.append(RawTrend(
            source_id="_catalog", raw_topic=raw_topic, title=raw_topic,
            description=f"{raw_topic} 관련 최근 관심 신호.", country=country, language=language,
            interest_series=series,
            engagement_signals={"cluster_hint": cluster, "shape": shape,
                                "risk_hint": risk, "competition_hint": comp,
                                "evergreen": evergreen,
                                "community_mentions": int(200 * j + 20)},
            source_metrics={"result_count": int(40 * j + 3),
                            "recent_uploads_7d": int(60 * j) if comp == "high" else int(12 * j)},
            reliability="mock",
            raw_payload={"catalog": True},
        ))
    return out


def slice_for_source(source_id: str, *, country: str, language: str, limit: int) -> list[RawTrend]:
    cat = build_catalog(country, language)
    # deterministic per-source rotation so different sources surface different topics
    off = int(hashlib.sha256(source_id.encode()).hexdigest()[:4], 16) % len(cat)
    rotated = cat[off:] + cat[:off]
    picked = rotated[: max(1, limit)]
    return [t.model_copy(update={"source_id": source_id}) for t in picked]
