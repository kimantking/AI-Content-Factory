"use client";

import { AGENTS, STATE_META, type AgentId, type OfficeModel } from "./office-data";
import { Icon } from "@/components/ui/Icon";

const ICON: Record<AgentId, Parameters<typeof Icon>[0]["name"]> = {
  research: "search",
  script: "edit",
  video: "film",
  publish: "send",
};

/**
 * 2.5D CSS fallback for mobile, reduced-motion, and no-WebGL. Same 4 stations,
 * same real state colours, fully interactive - no canvas.
 */
export function OfficeFallback({
  model,
  selected,
  onSelect,
}: {
  model: OfficeModel;
  selected: AgentId | null;
  onSelect: (id: AgentId | null) => void;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 [background-image:radial-gradient(ellipse_at_top,rgba(94,106,210,0.08),transparent_60%)]">
      <div className="grid grid-cols-2 gap-2.5">
        {AGENTS.map((a) => {
          const st = model.stations[a.id];
          const m = STATE_META[st];
          const on = selected === a.id;
          return (
            <button
              key={a.id}
              onClick={() => onSelect(on ? null : a.id)}
              aria-pressed={on}
              className={`group relative flex flex-col gap-2 rounded-md border p-3 text-left transition-colors ${
                on ? "border-primary bg-primary/10" : "border-hairline bg-surface-2 hover:border-hairline-strong"
              }`}
              style={{ perspective: "600px" }}
            >
              <span
                className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full"
                style={{ background: m.hex, boxShadow: `0 0 8px ${m.hex}` }}
              />
              <span
                className="flex h-9 w-9 items-center justify-center rounded-md border border-hairline bg-canvas text-ink-subtle transition-transform group-hover:[transform:rotateX(8deg)]"
                style={st === "RUNNING" ? { color: m.hex, borderColor: m.hex } : undefined}
              >
                <Icon name={ICON[a.id]} size={16} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-body-sm font-medium text-ink">{a.name}</span>
                <span className="block truncate text-caption text-ink-tertiary">{a.role}</span>
              </span>
              <span className="text-caption font-semibold" style={{ color: m.hex }}>
                {m.ko}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
