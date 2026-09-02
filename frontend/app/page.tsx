"use client";

import "./landing.css";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const PipelineScene = dynamic(() => import("@/components/landing/PipelineScene"), {
  ssr: false,
  loading: () => null,
});
const StudioRing = dynamic(() => import("@/components/landing/StudioRing"), {
  ssr: false,
  loading: () => null,
});

const STEPS = [
  "리서치", "팩트체크", "전략", "대본", "미디어", "편집",
  "검수", "예약", "게시", "분석", "학습",
];

const TILES: { t: string; d: string; big?: boolean; accent?: boolean; label: string }[] = [
  {
    label: "/A", t: "멀티 플랫폼", big: true,
    d: "YouTube · Shorts · TikTok · Instagram · Reels · Facebook · Threads · X · Pinterest · LinkedIn · 네이버 블로그 · 네이버 클립. 한 번 만들고 12곳에 맞춘다.",
  },
  { label: "/B", t: "로컬 AI", d: "Ollama · Gemma 로 로컬 처리. 반복 작업의 API 비용은 0." },
  { label: "/C", t: "거버넌스", d: "권리 · 저작권 · AI 표시 · 플랫폼 정책. 게시 전 6개 게이트를 통과해야 한다." },
  { label: "/D", t: "자율 학습", d: "에이전트가 스스로 좋은 자료를 찾고, 패턴을 배우고, 다음 제작에 적용한다." },
  { label: "/E", t: "비용 관제", d: "Provider · 모델별 실비용과 예산 한도. 모르는 단가는 0원이 아니라 '확인 필요'." },
  { label: "/F", t: "사람 검수", d: "승인 없이는 아무것도 게시되지 않는다. 마지막 결정은 언제나 사람." },
];

const FIGURES = [
  { n: "12", k: "플랫폼" },
  { n: "11", k: "제작 단계" },
  { n: "6", k: "검수 게이트" },
  { n: "0", k: "무단 게시" },
];

export default function Landing() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    const f = () => setReduced(m.matches);
    f();
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);

  return (
    <main className="landing">
      {/* ============================================ 00 · HERO */}
      <section className="stack-section relative flex flex-col justify-between overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <PipelineScene reduced={reduced} />
        </div>

        {/* horizontal translucent blur band passing over the scene */}
        <div className="relative z-[2] mt-[18vh] border-y border-[color:var(--hairline)] bg-[color:var(--paper)]/55 py-5 backdrop-blur-md">
          <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-6 px-[var(--gutter)]">
            <span className="t-label">하루에 수십 편 · 검수는 사람이</span>
            <span className="t-label hidden sm:inline">스튜디오 렌더 · 무채색 · 글로우 없음</span>
          </div>
        </div>

        <div className="relative z-[2] flex flex-1 items-start px-[var(--gutter)] pt-[6vh]">
          <span className="vlabel t-label mt-2">AI 콘텐츠 공장 &nbsp;®</span>
          <p className="ml-auto max-w-[46ch] pt-2 text-right t-lead">
            AI가 기획하고, 리서치하고, 대본을 쓰고, 영상을 만든다.
            <br />
            사람은 마지막에 결정만 한다.
          </p>
        </div>

        {/* oversized logotype, bleeds off both edges */}
        <h1 className="relative z-[2] -mx-[6vw] mb-[-1.5vw] whitespace-nowrap px-[var(--gutter)] t-hero">
          콘텐츠&nbsp;공장
        </h1>
      </section>

      {/* ============================================ 01 · 선언 */}
      <section className="stack-section flex flex-col justify-center overflow-hidden px-[var(--gutter)] py-[16vh]">
        <span className="t-label mb-8">/01 — 선언 &nbsp;·&nbsp; ©2026</span>
        <h2 className="-ml-[4vw] t-h2">
          많이 만드는 게 아니라
          <br />
          <span className="accent">제대로</span> 만든다.
        </h2>
        <p className="mt-10 max-w-[52ch] t-lead">
          속도는 도구가 낸다. 판단은 사람이 낸다. 이 제품은 그 경계를 흐리지 않는다.
        </p>
      </section>

      {/* ============================================ 02 · 생산 라인 */}
      <section className="stack-section px-[var(--gutter)] py-[14vh]">
        <span className="t-label">/02 — 생산 라인</span>
        <h3 className="mt-4 mb-10 t-h3">주제 하나가 게시까지 가는 길</h3>
        <ol>
          {STEPS.map((s, i) => (
            <li
              key={s}
              className="grid grid-cols-[auto_1fr_auto] items-baseline gap-x-6 border-t border-[color:var(--hairline)] py-4 last:border-b"
            >
              <span className="t-num !text-[clamp(28px,5vw,72px)] leading-none opacity-90">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="t-h3 !text-[clamp(20px,2.6vw,40px)]">{s}</span>
              <span className="t-label opacity-60">/STEP</span>
            </li>
          ))}
        </ol>
      </section>

      {/* ============================================ 03 · 역량 BENTO */}
      <section className="stack-section px-[var(--gutter)] py-[14vh]">
        <span className="t-label">/03 — 역량</span>
        <h3 className="mt-4 mb-10 t-h3">공장에 들어 있는 것</h3>
        <div className="grid auto-rows-[minmax(180px,auto)] grid-cols-1 gap-4 md:grid-cols-6">
          {TILES.map((c) => (
            <article
              key={c.t}
              className={`flex flex-col justify-between rounded-[var(--radius)] border border-[color:var(--hairline)] p-6 ${
                c.big ? "md:col-span-4 md:row-span-2" : "md:col-span-2"
              }`}
            >
              <span className="t-label opacity-60">{c.label}</span>
              <div>
                <h4 className={`${c.big ? "t-h2 !text-[clamp(32px,4.5vw,72px)]" : "t-h3"} mb-3`}>{c.t}</h4>
                <p className="max-w-[46ch] t-body opacity-80">{c.d}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ============================================ 04 · 지표 (오렌지) */}
      <section
        className="stack-section flex flex-col justify-center px-[var(--gutter)] py-[16vh]"
        style={{ background: "var(--accent)", color: "#0a0a0a", borderTopColor: "rgba(10,10,10,0.3)" }}
      >
        <span className="t-label" style={{ color: "#0a0a0a" }}>/04 — 지표 &nbsp;·&nbsp; LOCAL-FIRST</span>
        <div className="mt-10 grid grid-cols-2 gap-x-6 gap-y-14 md:grid-cols-4">
          {FIGURES.map((f) => (
            <div key={f.k}>
              <div className="t-num">{f.n}</div>
              <div className="t-label mt-3">{f.k}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ============================================ 05 · 재질 (STUDIO) */}
      <section className="stack-section grid grid-cols-1 overflow-hidden md:grid-cols-2">
        <div className="relative min-h-[60vh]">
          <div className="pointer-events-none absolute inset-0">
            <StudioRing reduced={reduced} />
          </div>
        </div>
        <div className="flex flex-col justify-center border-l border-[color:var(--hairline)] px-[var(--gutter)] py-[10vh]">
          <span className="t-label">/05 — 재질</span>
          <h3 className="mt-4 t-h3">스튜디오에서 찍은 것처럼</h3>
          <ul className="mt-8 space-y-3 t-body opacity-80">
            <li>무채색. 유광 블랙 또는 브러시드 크롬.</li>
            <li>소프트박스 3점 조명 + 부드러운 접지 그림자.</li>
            <li>네온 · 글로우 · 사이버펑크 없음.</li>
            <li>배경과 같은 오프화이트 위 — 오브젝트만 떠 보인다.</li>
          </ul>
        </div>
      </section>

      {/* ============================================ 06 · 운영 */}
      <section className="stack-section flex px-[var(--gutter)] py-[14vh]">
        <span className="vlabel t-label mr-8 shrink-0">운영</span>
        <div className="max-w-[62ch] space-y-8">
          <p className="t-h3">운영자 한 명이 공장 전체를 본다.</p>
          <p className="t-body opacity-80">
            지금 무엇이 작업 중인지, 어디가 막혔는지, 검수가 필요한지, 오늘 얼마를 썼는지 — 첫 화면에서 몇 초 안에 읽힌다.
          </p>
          <p className="t-body opacity-80">
            에이전트마다 현재 작업 · 모델 · Provider · 진행률 · 비용이 붙어 있다. 클릭하면 그 자리로 카메라가 이동한다.
          </p>
          <p className="t-body opacity-80">
            자율 학습은 게시와 분리되어 있다. AI가 배우는 것과 AI가 올리는 것은 절대 같이 켜지지 않는다.
          </p>
        </div>
      </section>

      {/* ============================================ 07 · CTA */}
      <section className="stack-section flex flex-col items-start justify-center px-[var(--gutter)] py-[18vh]">
        <span className="t-label mb-8">/06 — 지금</span>
        <Link
          href="/app"
          className="group inline-flex items-baseline gap-[0.15em] border-b-2 border-[color:var(--ink)] pb-2 t-hero !text-[clamp(48px,9vw,160px)] transition-transform hover:translate-x-1"
        >
          시작하기 <span className="accent">→</span>
        </Link>
        <p className="mt-8 max-w-[44ch] t-lead opacity-80">
          기존 대시보드는 그대로 <code className="t-label">/app</code> 에 있습니다.
        </p>
      </section>

      {/* ============================================ 08 · FOOTER */}
      <footer className="relative z-[1] border-t border-[color:var(--hairline)] bg-[color:var(--paper)] px-[var(--gutter)] pb-6 pt-14">
        <div className="mb-14 flex flex-wrap items-center justify-between gap-4">
          <nav className="flex flex-wrap gap-x-8 gap-y-2 t-label">
            <Link href="/app">대시보드</Link>
            <Link href="/app/create">만들기</Link>
            <Link href="/library">콘텐츠</Link>
            <Link href="/governance">검수</Link>
            <Link href="/support">AI 지원</Link>
          </nav>
          <span className="t-label opacity-60">©2026 &nbsp;·&nbsp; ® &nbsp;·&nbsp; /END</span>
        </div>
        <div className="overflow-hidden">
          <span className="block whitespace-nowrap t-hero !text-[clamp(64px,16vw,260px)] opacity-[0.9]">
            AI&nbsp;콘텐츠&nbsp;공장
          </span>
        </div>
      </footer>
    </main>
  );
}
