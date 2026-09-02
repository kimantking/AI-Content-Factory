"use client";

import { AGENTS, STATE_META, type AgentId, type OfficeModel } from "./office-data";

const POSITIONS: Record<AgentId, { left: string; top: string; delay: string }> = {
  research: { left: "17%", top: "64%", delay: "0s" },
  script: { left: "33%", top: "54%", delay: "-.7s" },
  video: { left: "68%", top: "54%", delay: "-1.3s" },
  publish: { left: "83%", top: "64%", delay: "-1.9s" },
};

export function RealisticOffice({
  model,
  selected,
  onSelect,
  reducedMotion,
}: {
  model: OfficeModel;
  selected: AgentId | null;
  onSelect: (id: AgentId | null) => void;
  reducedMotion: boolean;
}) {
  return (
    <div className="relative h-full w-full overflow-hidden bg-[#f5d7e5]">
      <img
        src="/studio-office-real.png"
        alt="통창과 파스텔 핑크 조명이 있는 실제 사무실"
        className="absolute inset-0 h-full w-full object-cover object-center"
        draggable={false}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-[#fff2f8]/10 via-transparent to-[#351d2a]/30" />

      {AGENTS.map((agent) => {
        const state = model.stations[agent.id];
        const meta = STATE_META[state];
        const pos = POSITIONS[agent.id];
        const active = state === "RUNNING";
        const chosen = selected === agent.id;
        return (
          <button
            key={agent.id}
            type="button"
            aria-label={`${agent.name} · ${meta.ko}`}
            aria-pressed={chosen}
            onClick={() => onSelect(chosen ? null : agent.id)}
            className={`group absolute -translate-x-1/2 -translate-y-1/2 text-center outline-none ${
              reducedMotion ? "" : "office-agent"
            }`}
            style={{ left: pos.left, top: pos.top, animationDelay: pos.delay }}
          >
            <span className={`relative mx-auto block w-[70px] sm:w-[96px] lg:w-[112px] ${active && !reducedMotion ? "agent-working" : ""}`}>
              <span
                className="absolute inset-1 rounded-full blur-xl"
                style={{ background: meta.hex, opacity: active ? 0.62 : 0.2 }}
              />
              <img src="/studio-agent-pixel.png" alt="" className="relative block w-full drop-shadow-[0_8px_8px_rgba(30,12,24,.42)] [image-rendering:pixelated]" draggable={false} />
              <span
                className="absolute right-0 top-0 h-3 w-3 rounded-full border-2 border-white shadow"
                style={{ background: meta.hex }}
              />
            </span>
            <span className={`mt-1.5 inline-flex rounded-md border px-2 py-1 backdrop-blur-md transition ${
              chosen ? "border-primary bg-primary text-white" : "border-white/60 bg-white/75 text-[#4b3342] group-hover:bg-white"
            }`}>
              <span className="text-[11px] font-semibold sm:text-xs">{agent.name} · {meta.ko}</span>
            </span>
          </button>
        );
      })}

      <style jsx>{`
        .office-agent { animation: float-agent 3.4s ease-in-out infinite; }
        .agent-working { animation: type-agent .42s steps(2, end) infinite; }
        @keyframes float-agent { 0%, 100% { margin-top: 0; } 50% { margin-top: -7px; } }
        @keyframes type-agent { 0%, 100% { transform: translateX(-1px) rotate(-1deg); } 50% { transform: translateX(1px) rotate(1deg); } }
      `}</style>
    </div>
  );
}
