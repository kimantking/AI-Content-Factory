"use client";

import { AGENTS, STATE_META, type AgentId, type OfficeModel } from "./office-data";

export function RealisticOffice({ model, selected, onSelect }: {
  model: OfficeModel;
  selected: AgentId | null;
  onSelect: (id: AgentId | null) => void;
  reducedMotion: boolean;
}) {
  return (
    <div className="studio-sky h-full overflow-auto px-4 pb-6 pt-8 sm:px-8 sm:pt-10">
      <div className="mx-auto max-w-5xl">
        <p className="text-xs font-semibold tracking-[.18em] text-[#88647b]">나의 AI 제작팀</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[#392d43] sm:text-3xl">좋은 이야기를, 함께 만들어요.</h2>
        <p className="mt-2 text-sm text-[#6e5a72]">담당 에이전트를 선택해 아이디어와 제작 방향을 이야기하세요.</p>
        <div className="mt-6 grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
          {AGENTS.map((agent) => {
            const meta = STATE_META[model.stations[agent.id]];
            const chosen = selected === agent.id;
            return (
              <button key={agent.id} type="button" aria-pressed={chosen}
                aria-label={`${agent.name}, ${meta.ko}, 대화 열기`}
                onClick={() => onSelect(chosen ? null : agent.id)}
                className={`agent-person group relative overflow-hidden rounded-2xl border bg-white/75 text-left transition hover:-translate-y-1 hover:bg-white/95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#956182] ${chosen ? "border-[#956182]" : "border-white/90"}`}>
                <div className="relative h-32 overflow-hidden bg-gradient-to-br from-[#fff8ee] via-[#fae7ee] to-[#dedff1] sm:h-44 lg:h-56">
                  <img src={`/agent-${agent.id}.webp`} alt="" draggable={false}
                    className="absolute left-1/2 top-1 w-[90%] max-w-none -translate-x-1/2" />
                  <span className="absolute bottom-2 left-2 inline-flex items-center gap-1.5 rounded-full bg-white/95 px-2.5 py-1 text-[11px] text-[#49384e]">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.hex }} />{meta.ko}
                  </span>
                </div>
                <div className="p-3 sm:p-4">
                  <h3 className="text-sm font-semibold text-[#392d43] sm:text-base">{agent.name}</h3>
                  <p className="mt-1 text-[11px] text-[#79667f] sm:text-xs">{agent.role}</p>
                  <span className="mt-3 flex items-center justify-between border-t border-[#eadde6] pt-3 text-xs font-semibold text-[#915573]">대화하기 <span aria-hidden="true">↗</span></span>
                </div>
              </button>
            );
          })}
        </div>
        <p className="mt-4 text-xs text-[#79667f]">AI 에이전트 · 작업 상태는 연결된 제작 파이프라인을 기준으로 표시됩니다.</p>
      </div>
    </div>
  );
}
