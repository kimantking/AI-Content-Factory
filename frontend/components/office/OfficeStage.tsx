"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { SupportSnapshot } from "@/lib/api";
import { deriveOffice, type AgentId } from "./office-data";
import { OfficeFallback } from "./OfficeFallback";
import { AgentPanel } from "./AgentPanel";
import { Icon } from "@/components/ui/Icon";

const Office3D = dynamic(() => import("./Office3D"), {
  ssr: false,
  loading: () => <StageSkeleton />,
});

function StageSkeleton() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <span className="flex items-center gap-2 text-caption text-ink-tertiary">
        <Icon name="layers" size={14} className="animate-pulse" />
        스튜디오 준비 중…
      </span>
    </div>
  );
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl") || c.getContext("experimental-webgl")));
  } catch {
    return false;
  }
}

/* radial + vertical mask so the rendered scene dissolves into the page - no box, no border */
const SCENE_MASK =
  "linear-gradient(to bottom, transparent 0%, #000 8%, #000 88%, transparent 100%)";

export function OfficeStage({ snap, overlay }: { snap: SupportSnapshot | null; overlay?: ReactNode }) {
  const model = useMemo(() => deriveOffice(snap), [snap]);
  const [selected, setSelected] = useState<AgentId | null>(null);
  const [mode, setMode] = useState<"pending" | "3d" | "fallback">("pending");
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const wide = window.matchMedia("(min-width: 768px)");
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const decide = () => {
      setReducedMotion(rm.matches);
      setMode(wide.matches && hasWebGL() ? "3d" : "fallback");
    };
    decide();
    wide.addEventListener("change", decide);
    rm.addEventListener("change", decide);
    return () => {
      wide.removeEventListener("change", decide);
      rm.removeEventListener("change", decide);
    };
  }, []);

  return (
    <section aria-label="AI 오퍼레이션 스튜디오" className="relative -mx-4 -mt-4 sm:-mx-6 sm:-mt-6">
      {/* the studio is a full-bleed spatial band, not a widget */}
      <div className="relative h-[390px] sm:h-[500px] lg:h-[620px]">
        {mode === "3d" ? (
          <div
            className="absolute inset-0"
            style={{ WebkitMaskImage: SCENE_MASK, maskImage: SCENE_MASK }}
          >
            <Office3D model={model} selected={selected} onSelect={setSelected} reducedMotion={reducedMotion} />
          </div>
        ) : mode === "fallback" ? (
          <div className="h-full overflow-y-auto px-4 pt-2 sm:px-6">
            <p className="t-eyebrow mb-2">
              오퍼레이션 스튜디오 · {model.hasJob ? "AI 에이전트 작업 중" : "모든 에이전트 대기"}
            </p>
            <OfficeFallback model={model} selected={selected} onSelect={setSelected} />
          </div>
        ) : (
          <StageSkeleton />
        )}

        {/* floating status label (desktop) */}
        {mode === "3d" && (
          <div className="pointer-events-none absolute left-4 top-6 hidden items-center gap-3 sm:left-6 sm:flex">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-primary">Live studio / 002</span>
            <span className="text-caption text-ink-tertiary">
              {model.hasJob ? "AI 에이전트 작업 중" : "모든 에이전트 대기"}
            </span>
          </div>
        )}

        {/* content that floats over the studio (e.g. the command composer) */}
        {overlay && (
          <div className="pointer-events-none absolute inset-x-0 top-0 px-4 sm:px-6">
            <div className="pointer-events-auto mx-auto max-w-workspace">{overlay}</div>
          </div>
        )}

        {selected && (
          <div className="absolute inset-x-0 bottom-0 flex justify-center p-3 sm:inset-auto sm:right-6 sm:top-4 sm:block sm:p-0">
            <AgentPanel id={selected} model={model} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </section>
  );
}
