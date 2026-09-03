"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { SupportSnapshot } from "@/lib/api";
import { deriveOffice, type AgentId } from "./office-data";
import { RealisticOffice } from "./RealisticOffice";
import { AgentPanel } from "./AgentPanel";

export function OfficeStage({ snap, overlay }: { snap: SupportSnapshot | null; overlay?: ReactNode }) {
  const model = useMemo(() => deriveOffice(snap), [snap]);
  const [selected, setSelected] = useState<AgentId | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const decide = () => setReducedMotion(rm.matches);
    decide();
    rm.addEventListener("change", decide);
    return () => {
      rm.removeEventListener("change", decide);
    };
  }, []);

  return (
    <section aria-label="AI 오퍼레이션 스튜디오" className="relative -mx-4 -mt-4 sm:-mx-6 sm:-mt-6">
      {/* the studio is a full-bleed spatial band, not a widget */}
      <div className="relative h-[360px] sm:h-[500px] lg:h-[620px]">
        <RealisticOffice model={model} selected={selected} onSelect={setSelected} reducedMotion={reducedMotion} />

        {/* floating status label (desktop) */}
        <div className="pointer-events-none absolute left-4 top-6 hidden items-center gap-3 sm:left-6 sm:flex">
          <span className="rounded-md border border-white/60 bg-white/75 px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.18em] text-primary backdrop-blur-md">Live studio / 002</span>
          <span className="rounded-md bg-white/70 px-2.5 py-1 text-caption text-[#62485a] backdrop-blur-md">
            {model.hasJob ? "AI 에이전트 작업 중" : "모든 에이전트 대기"}
          </span>
        </div>

        {/* content that floats over the studio (e.g. the command composer) */}
        {overlay && (
          <div className="pointer-events-none absolute inset-x-0 top-0 px-4 sm:px-6">
            <div className="pointer-events-auto mx-auto max-w-workspace">{overlay}</div>
          </div>
        )}

        {selected && (
          <>
            <button
              type="button"
              aria-label="에이전트 대화창 닫기"
              onClick={() => setSelected(null)}
              className="fixed inset-0 z-[90] cursor-default bg-[#2d1723]/25 backdrop-blur-[2px] sm:absolute sm:z-20"
            />
            <div className="fixed inset-0 z-[100] flex justify-center sm:absolute sm:inset-auto sm:right-6 sm:top-4 sm:z-40 sm:block">
              <AgentPanel id={selected} model={model} onClose={() => setSelected(null)} />
            </div>
          </>
        )}
      </div>
    </section>
  );
}
