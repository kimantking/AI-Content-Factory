"use client";

import { useTheme } from "@/lib/theme";
import { Icon } from "./Icon";

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "라이트" : "다크";
  return (
    <button
      type="button"
      onClick={toggle}
      className="btn btn-ghost !px-2"
      aria-label={`${next} 모드로 전환`}
      title={`${next} 모드로 전환`}
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
      {!compact && <span className="text-caption">{next} 모드</span>}
    </button>
  );
}
