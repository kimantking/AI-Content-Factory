import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

/* ------------------------------------------------------------------ Card */
export function Card({
  children,
  className = "",
  lift,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  lift?: boolean;
  as?: "div" | "section" | "article";
}) {
  return (
    <Tag className={`card ${lift ? "card-2" : ""} ${className}`}>{children}</Tag>
  );
}

export function CardBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card-p ${className}`}>{children}</div>;
}

export function CardTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="text-body-sm font-semibold text-ink">{children}</h2>
      {sub != null && <span className="text-caption text-ink-subtle">{sub}</span>}
    </div>
  );
}

/* ------------------------------------------------------------ PageHeader */
export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
}: {
  title: string;
  eyebrow?: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="t-eyebrow mb-1">{eyebrow}</p>}
        <h1 className="font-display text-[21px] font-semibold leading-tight tracking-[-0.5px] text-ink sm:text-[26px] sm:tracking-[-0.6px]">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 max-w-[68ch] text-body-sm text-ink-subtle">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

/* ---------------------------------------------------------------- Metric */
export function Metric({
  label,
  value,
  hint,
  size = "md",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  const v =
    size === "lg" ? "text-[28px] leading-none" : size === "sm" ? "text-[18px] leading-none" : "text-[22px] leading-none";
  return (
    <div className="min-w-0">
      <p className="text-caption text-ink-subtle">{label}</p>
      <p className={`mt-1.5 font-display font-semibold tabular-nums tracking-[-0.5px] text-ink ${v}`}>
        {value}
      </p>
      {hint != null && <p className="mt-1 text-caption text-ink-tertiary">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------ EmptyState */
export function EmptyState({
  icon = "sparkles",
  title,
  body,
  action,
}: {
  icon?: IconName;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-hairline px-6 py-9 text-center">
      <span className="mb-2.5 flex h-9 w-9 items-center justify-center rounded-full bg-surface-2 text-ink-subtle">
        <Icon name={icon} size={17} />
      </span>
      <p className="text-body-sm font-semibold text-ink">{title}</p>
      {body && <p className="mt-1 max-w-[42ch] text-body-sm text-ink-subtle">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------ ErrorState */
export function ErrorState({
  title = "문제가 발생했습니다",
  detail,
  recovering,
  action,
  onRetry,
}: {
  title?: string;
  detail?: ReactNode;
  recovering?: boolean;
  action?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-lg border border-hairline-strong bg-surface-2 px-4 py-4">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex-shrink-0 text-ink">
          <Icon name="alert" size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-body-sm font-semibold text-ink">{title}</p>
          {detail && <p className="mt-1 break-words text-body-sm text-ink-subtle">{detail}</p>}
          <p className="mt-1 text-caption text-ink-tertiary">
            {recovering ? "시스템이 자동으로 복구를 시도하고 있습니다." : "잠시 후 다시 시도하거나 AI 지원 스냅샷을 확인하세요."}
          </p>
          {(action || onRetry) && (
            <div className="mt-3 flex gap-2">
              {onRetry && (
                <button className="btn btn-secondary" onClick={onRetry}>
                  <Icon name="refresh" size={15} />
                  다시 시도
                </button>
              )}
              {action}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- Skeleton */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-2 ${className}`} />;
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-3.5 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}
