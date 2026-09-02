import { Icon } from "./Icon";
import { statusMeta, TONE_DOT, TONE_TEXT, type Tone } from "@/lib/status";

/** Enum -> ko label + icon + subtle tint. Never colour-only. */
export function StatusBadge({
  value,
  size = "md",
  className = "",
}: {
  value: string | null | undefined;
  size?: "sm" | "md";
  className?: string;
}) {
  const m = statusMeta(value);
  return (
    <span
      className={`chip ${TONE_TEXT[m.tone]} ${size === "sm" ? "!px-2 !py-0.5 !text-[11px]" : ""} ${className}`}
      title={value ?? undefined}
    >
      <Icon name={m.icon} size={size === "sm" ? 12 : 13} />
      {m.ko}
    </span>
  );
}

/** Compact dot + text, for dense rows and nav. */
export function StatusDot({ value, label }: { value: string | null | undefined; label?: string }) {
  const m = statusMeta(value);
  return (
    <span className="inline-flex items-center gap-1.5 text-body-sm">
      <span className={`h-2 w-2 flex-shrink-0 rounded-full ${TONE_DOT[m.tone]}`} />
      <span className={TONE_TEXT[m.tone]}>{label ?? m.ko}</span>
    </span>
  );
}

export function toneClass(tone: Tone) {
  return TONE_TEXT[tone];
}
