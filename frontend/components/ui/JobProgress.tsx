import { Icon } from "./Icon";
import { statusMeta, TONE_DOT, TONE_TEXT } from "@/lib/status";

export type JobStep = { key: string; label: string; state: string };

/** Canonical high-level pipeline (Home / AI Support coarse view). */
export const PIPELINE_STAGES: { key: string; label: string }[] = [
  { key: "research", label: "리서치" },
  { key: "fact_check", label: "팩트체크" },
  { key: "strategy", label: "전략" },
  { key: "script", label: "대본" },
  { key: "media", label: "미디어" },
  { key: "render", label: "렌더링" },
  { key: "governance", label: "거버넌스" },
  { key: "publish", label: "게시" },
];

/**
 * Horizontal stepper on desktop, vertical on mobile. Pure presentation - the
 * caller maps backend status strings into JobStep.state.
 */
export function JobProgress({ steps, dense = false }: { steps: JobStep[]; dense?: boolean }) {
  return (
    <ol
      className={`flex flex-col gap-0 sm:flex-row sm:items-start sm:gap-0 ${
        dense ? "" : ""
      }`}
    >
      {steps.map((s, i) => {
        const m = statusMeta(s.state);
        const last = i === steps.length - 1;
        const running = m.tone === "run";
        return (
          <li key={s.key} className="flex flex-1 gap-3 sm:flex-col sm:gap-2">
            {/* rail */}
            <div className="flex flex-col items-center sm:w-full sm:flex-row">
              <span
                className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border ${
                  running
                    ? "border-primary text-primary"
                    : m.tone === "ok"
                      ? "border-success/40 text-success"
                      : m.tone === "error" || m.tone === "block"
                        ? "border-hairline-strong text-ink"
                        : "border-hairline text-ink-tertiary"
                }`}
              >
                <Icon name={m.icon} size={13} className={running ? "animate-pulse" : ""} />
              </span>
              <span
                className={`my-1 w-px flex-1 sm:my-0 sm:mx-1 sm:h-px sm:w-full ${
                  last ? "bg-transparent" : m.tone === "ok" ? "bg-success/30" : "bg-hairline"
                }`}
              />
            </div>
            {/* label */}
            <div className="pb-4 sm:pb-0">
              <p className={`text-body-sm font-medium ${running ? "text-ink" : "text-ink-muted"}`}>
                {s.label}
              </p>
              <p className={`text-caption ${TONE_TEXT[m.tone]}`}>{m.ko}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Small live-status line: agent / model / elapsed etc. */
export function JobMeta({ items }: { items: { k: string; v: string | number | null | undefined }[] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
      {items.map(({ k, v }) => (
        <div key={k}>
          <dt className="text-caption text-ink-subtle">{k}</dt>
          <dd className="mt-0.5 truncate font-mono text-[12px] text-ink">{v ?? "-"}</dd>
        </div>
      ))}
    </dl>
  );
}

export { TONE_DOT };
