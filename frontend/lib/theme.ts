"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

/** Read/observe the theme that layout.tsx's pre-paint script already applied. */
export function useTheme(): { theme: Theme; toggle: () => void; set: (t: Theme) => void } {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const cur = (document.documentElement.getAttribute("data-theme") as Theme) || "dark";
    setThemeState(cur);
  }, []);

  const set = useCallback((t: Theme) => {
    document.documentElement.setAttribute("data-theme", t);
    try {
      localStorage.setItem("acf-theme", t);
    } catch {
      /* private mode - ignore */
    }
    setThemeState(t);
  }, []);

  const toggle = useCallback(() => set(theme === "dark" ? "light" : "dark"), [theme, set]);

  return { theme, toggle, set };
}
