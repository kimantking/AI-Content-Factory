"use client";

import { useCallback } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

export type Column<T> = {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  width?: string;
  hideBelow?: "sm" | "md" | "lg";
};

export function DataTable<T>({
  columns,
  rows,
  getKey,
  onRowClick,
  empty,
}: {
  columns: Column<T>[];
  rows: T[];
  getKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
}) {
  const hide = (c?: "sm" | "md" | "lg") =>
    c === "sm" ? "hidden sm:table-cell" : c === "md" ? "hidden md:table-cell" : c === "lg" ? "hidden lg:table-cell" : "";
  return (
    <div className="overflow-x-auto rounded-lg border border-hairline">
      <table className="w-full border-collapse text-body-sm">
        <thead>
          <tr className="border-b border-hairline bg-surface-2 text-left">
            {columns.map((c) => (
              <th
                key={c.key}
                style={{ width: c.width }}
                className={`px-3 py-2.5 text-caption font-medium text-ink-subtle ${
                  c.align === "right" ? "text-right" : ""
                } ${hide(c.hideBelow)}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-10 text-center text-body-sm text-ink-subtle">
                {empty ?? "표시할 항목이 없습니다."}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={getKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? "button" : undefined}
                className={`border-b border-hairline last:border-0 ${
                  onRowClick ? "cursor-pointer hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-focus/50" : ""
                }`}
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={`px-3 py-2.5 text-ink-muted ${c.align === "right" ? "text-right tabular-nums" : ""} ${hide(
                      c.hideBelow,
                    )}`}
                  >
                    {c.cell(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({
  page,
  pages,
  onPage,
}: {
  page: number;
  pages: number;
  onPage: (p: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <nav className="flex items-center justify-center gap-3 text-body-sm" aria-label="페이지 이동">
      <button
        className="btn btn-secondary !px-2"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        aria-label="이전 페이지"
      >
        <Icon name="chevron-left" size={15} />
        이전
      </button>
      <span className="tabular-nums text-ink-subtle">
        {page} / {pages}
      </span>
      <button
        className="btn btn-secondary !px-2"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
        aria-label="다음 페이지"
      >
        다음
        <Icon name="chevron-right" size={15} />
      </button>
    </nav>
  );
}

/** Sync a small set of filter keys to the URL query string (shallow). */
export function useUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const get = useCallback((key: string, fallback = "") => params.get(key) ?? fallback, [params]);

  const setMany = useCallback(
    (patch: Record<string, string | number | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === "" || v === undefined) next.delete(k);
        else next.set(k, String(v));
      }
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );

  return { get, setMany };
}
