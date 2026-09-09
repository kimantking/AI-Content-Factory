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
      <div className="relative h-[710px] sm:h-[820px] lg:h-[590px]">
        <RealisticOffice model={model} selected={selected} onSelect={setSelected} reducedMotion={reducedMotion} />

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
              className="fixed inset-0 z-[90] cursor-default bg-[#2d1723]/25 backdrop-blur-[2px]"
            />
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-0 sm:p-6">
              <AgentPanel key={`${selected}:${model.job.campaignId ?? "general"}`} id={selected} model={model} onClose={() => setSelected(null)} />
            </div>
          </>
        )}
      </div>
    </section>
  );
}
