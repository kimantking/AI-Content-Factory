import type { SVGProps } from "react";

/**
 * One hand-tuned line-icon family (stroke 1.75, 24-grid, currentColor).
 * The project forbids adding an icon package, so this is the single source.
 * Keep strokes consistent; do not inline ad-hoc paths in screens.
 */
export type IconName =
  | "home" | "library" | "plus" | "check" | "shield" | "activity" | "clock"
  | "alert" | "lock" | "x" | "dot" | "pause" | "calendar" | "send" | "edit"
  | "search" | "command" | "bell" | "chevron-left" | "chevron-right"
  | "chevron-down" | "panel-left" | "sun" | "moon" | "sparkles" | "film"
  | "cpu" | "coin" | "chart" | "rocket" | "folder" | "settings" | "life-buoy"
  | "external" | "arrow-right" | "more" | "layers" | "zap" | "refresh"
  | "copy" | "eye" | "server" | "book";

const P: Record<IconName, string> = {
  home: "M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5",
  library: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  plus: "M12 5v14M5 12h14",
  check: "M20 6 9 17l-5-5",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  activity: "M3 12h4l3 8 4-16 3 8h4",
  clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  alert: "M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  lock: "M6 11V8a6 6 0 1 1 12 0v3M5 11h14v10H5z",
  x: "M18 6 6 18M6 6l12 12",
  dot: "M12 12h.01",
  pause: "M8 5v14M16 5v14",
  calendar: "M4 6h16v15H4zM4 10h16M8 3v4M16 3v4",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z",
  search: "M21 21l-4.3-4.3M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0z",
  command: "M9 9V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v3m0 6v3a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3v-3m0-6h6v6H9z",
  bell: "M18 9a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8M13.7 21a2 2 0 0 1-3.4 0",
  "chevron-left": "M15 18l-6-6 6-6",
  "chevron-right": "M9 18l6-6-6-6",
  "chevron-down": "M6 9l6 6 6-6",
  "panel-left": "M4 4h16v16H4zM10 4v16",
  sun: "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  sparkles: "M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.9 2.3 2.3.9-2.3.9L19 21l-.9-2.3-2.3-.9 2.3-.9z",
  film: "M3 4h18v16H3zM7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4",
  cpu: "M6 6h12v12H6zM9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2",
  coin: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5c0-1.2 1.1-2 2.5-2s2.5.8 2.5 2-1.1 1.6-2.5 2-2.5.9-2.5 2 1.1 2 2.5 2 2.5-.8 2.5-2M12 6v1.5M12 16.5V18",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  rocket: "M5 13c-1.5 1.3-2 5-2 5s3.7-.5 5-2M9 15l-3-3c1-5 5-9 12-9 0 7-4 11-9 12zM14 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
  folder: "M3 6h6l2 3h10v10H3z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 13a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.3a2 2 0 0 1-4 0v-.2a1.6 1.6 0 0 0-2.7-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 4.6 13H4a2 2 0 0 1 0-4h.2A1.6 1.6 0 0 0 5.3 6.3l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 11 3.6V4a2 2 0 0 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8 1.6 1.6 0 0 0 1.5 1H23a2 2 0 0 1 0 4h-.2a1.6 1.6 0 0 0-1.4 1z",
  "life-buoy": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM4.9 4.9l4.3 4.3M14.8 14.8l4.3 4.3M14.8 9.2l4.3-4.3M4.9 19.1l4.3-4.3",
  external: "M14 4h6v6M20 4l-9 9M10 4H4v16h16v-6",
  "arrow-right": "M5 12h14M13 6l6 6-6 6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  layers: "M12 3 3 8l9 5 9-5-9-5zM3 14l9 5 9-5",
  zap: "M13 2 4 14h7l-1 8 9-12h-7z",
  refresh: "M21 12a9 9 0 1 1-3-6.7M21 5v4h-4",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  server: "M3 4h18v6H3zM3 14h18v6H3zM7 7h.01M7 17h.01",
  book: "M4 5a2 2 0 0 1 2-2h14v18H6a2 2 0 0 0-2 2zM4 21a2 2 0 0 1 2-2h14",
};

export function Icon({
  name,
  size = 18,
  className,
  ...rest
}: { name: IconName; size?: number } & Omit<SVGProps<SVGSVGElement>, "name">) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      {...rest}
    >
      <path d={P[name]} />
    </svg>
  );
}
