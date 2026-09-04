"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DlqRow,
  OpsStatus,
  checkCostAnomaly,
  getOpsBackups,
  getOpsDlq,
  getOpsQueues,
  getOpsStatus,
  opsScanStuck,
  resolveOpsAlert,
  resolveOpsDlq,
  retryOpsDlq,
  runOpsBackup,
  scanStorageIntegrity,
  setOpsFlag,
  verifyOpsBackup,
} from "@/lib/api";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-hairline bg-surface-1 p-5">
      <h2 className="mb-3 text-sm font-bold">{title}</h2>
      {children}
    </section>
  );
}

const TONE: Record<string, string> = {
  OK: "text-success",
  HEALTHY: "text-success",
  NORMAL: "text-success",
  WARNING: "text-brand-secure",
  SLOW: "text-brand-secure",
  STALE: "text-brand-secure",
  DEGRADED: "text-brand-secure",
  CRITICAL: "text-brand-secure",
  HOLD: "text-brand-secure",
  DEAD: "text-brand-secure",
  ERROR: "text-brand-secure",
};

function Dot({ status }: { status: string }) {
  return <span className={`font-mono text-xs font-bold ${TONE[status] ?? "text-ink-subtle"}`}>{status}</span>;
}

export default function AdminPage() {
  const [st, setSt] = useState<OpsStatus | null>(null);
  const [queues, setQueues] = useState<Record<string, unknown> | null>(null);
  const [backups, setBackups] = useState<Record<string, unknown> | null>(null);
  const [dlq, setDlq] = useState<DlqRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, q, b, d] = await Promise.all([
        getOpsStatus(),
        getOpsQueues(),
        getOpsBackups(),
        getOpsDlq("OPEN"),
      ]);
      setSt(s);
      setQueues(q);
      setBackups(b);
      setDlq(d);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  async function act(label: string, fn: () => Promise<unknown>, confirmMsg?: string) {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setBusy(true);
    setErr(null);
    setNote(null);
    try {
      const r = await fn();
      setNote(`${label}: ${JSON.stringify(r).slice(0, 400)}`);
      await load();
    } catch (e) {
      setErr(`${label} failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  const flagOn = (name: string) => {
    const f = (st?.flags?.[name] ?? {}) as Record<string, unknown>;
    return Boolean(f.enabled);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-3">
        <h1 className="text-lg font-bold">시스템 운영</h1>
        {st && (
          <span className="text-xs text-subtle">
            {st.env} · v{st.version} · 15초마다 자동 갱신
          </span>
        )}
        <button
          className="ml-auto rounded-lg border px-3 py-1 text-xs disabled:opacity-50"
          disabled={busy}
          onClick={load}
        >
          지금 새로고침
        </button>
      </div>

      {err && <p className="rounded-lg bg-surface-2 p-3 text-xs text-brand-secure">{err}</p>}
      {note && <p className="rounded-lg bg-surface-2 p-3 font-mono text-xs text-ink-muted">{note}</p>}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="시스템 상태">
          {st ? (
            <table className="w-full text-xs">
              <tbody>
                {Object.entries(st.dependencies).map(([k, v]) => (
                  <tr key={k} className="border-b border-hairline last:border-0">
                    <td className="py-1 pr-3 font-medium capitalize">{k}</td>
                    <td className="py-1 pr-3">
                      <Dot status={String((v as Record<string, unknown>).status ?? "?")} />
                    </td>
                    <td className="py-1 text-ink-subtle">
                      {String((v as Record<string, unknown>).detail ?? "")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-xs text-subtle">loading…</p>
          )}
        </Card>

        <Card title="런타임 플래그">
          {st ? (
            <div className="space-y-2 text-xs">
              <FlagRow
                name="EMERGENCY_STOP"
                on={flagOn("EMERGENCY_STOP")}
                locked
                hint="toggle from the Autopilot page"
              />
              <FlagRow
                name="SAFE_MODE"
                on={flagOn("SAFE_MODE")}
                busy={busy}
                onToggle={(next) =>
                  act(
                    `SAFE_MODE=${next}`,
                    () => setOpsFlag("SAFE_MODE", next, true),
                    next ? "Enable SAFE_MODE? Autopilot production will HOLD." : undefined,
                  )
                }
              />
              <FlagRow
                name="MAINTENANCE_MODE"
                on={flagOn("MAINTENANCE_MODE")}
                busy={busy}
                onToggle={(next) =>
                  act(
                    `MAINTENANCE_MODE=${next}`,
                    () => setOpsFlag("MAINTENANCE_MODE", next, true),
                    next ? "Enable MAINTENANCE_MODE? The API will return 503 for app routes." : undefined,
                  )
                }
              />
            </div>
          ) : (
            <p className="text-xs text-subtle">loading…</p>
          )}
        </Card>

        <Card title="작업자">
          {st && st.workers.length ? (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-tertiary">
                  <th className="py-1 pr-2">작업자</th>
                  <th className="py-1 pr-2">상태</th>
                  <th className="py-1 pr-2">job</th>
                  <th className="py-1">하트비트</th>
                </tr>
              </thead>
              <tbody>
                {st.workers.map((w) => (
                  <tr key={w.worker_id} className="border-b border-hairline last:border-0">
                    <td className="py-1 pr-2 font-mono">{w.worker_id.slice(0, 18)}</td>
                    <td className="py-1 pr-2">
                      <Dot status={w.status} />
                    </td>
                    <td className="py-1 pr-2 font-mono text-ink-subtle">{w.current_job ?? "—"}</td>
                    <td className="py-1 text-ink-subtle">{w.last_heartbeat?.replace("T", " ").slice(0, 19)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-xs text-subtle">활성 작업자 없음</p>
          )}
          <button
            className="mt-3 rounded-lg border px-3 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={() => act("scan-stuck", opsScanStuck)}
          >
            Scan stuck jobs
          </button>
        </Card>

        <Card title="큐 · 백프레셔">
          {queues ? (
            <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-xs">
              {JSON.stringify(queues, null, 2)}
            </pre>
          ) : (
            <p className="text-xs text-subtle">loading…</p>
          )}
        </Card>
      </div>

      <Card title="미해결 알림">
        {st && st.open_alerts.length ? (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-tertiary">
                <th className="py-1 pr-2">심각도</th>
                <th className="py-1 pr-2">key</th>
                <th className="py-1 pr-2">메시지</th>
                <th className="py-1 pr-2">횟수</th>
                <th className="py-1"></th>
              </tr>
            </thead>
            <tbody>
              {st.open_alerts.map((a) => (
                <tr key={a.id} className="border-b border-hairline last:border-0">
                  <td className="py-1 pr-2">
                    <Dot status={a.severity} />
                  </td>
                  <td className="py-1 pr-2 font-mono">{a.key}</td>
                  <td className="py-1 pr-2">{a.message}</td>
                  <td className="py-1 pr-2">{a.count}</td>
                  <td className="py-1">
                    <button
                      className="rounded border px-2 py-0.5 disabled:opacity-50"
                      disabled={busy}
                      onClick={() => act(`resolve ${a.key}`, () => resolveOpsAlert(a.id))}
                    >
                      resolve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-xs text-success">미해결 알림 없음</p>
        )}
      </Card>

      <Card title={`Failed Jobs / DLQ (${dlq.length} open)`}>
        {dlq.length ? (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-tertiary">
                <th className="py-1 pr-2">kind</th>
                <th className="py-1 pr-2">job</th>
                <th className="py-1 pr-2">사유</th>
                <th className="py-1 pr-2">오류</th>
                <th className="py-1 pr-2">시도</th>
                <th className="py-1"></th>
              </tr>
            </thead>
            <tbody>
              {dlq.map((d) => (
                <tr key={d.id} className="border-b border-hairline last:border-0">
                  <td className="py-1 pr-2 font-mono">{d.job_kind}</td>
                  <td className="py-1 pr-2 font-mono text-ink-subtle">{d.job_id}</td>
                  <td className="py-1 pr-2">{d.reason}</td>
                  <td className="py-1 pr-2 font-mono">{d.error_type ?? "—"}</td>
                  <td className="py-1 pr-2">{d.attempts}</td>
                  <td className="py-1 space-x-1">
                    <button
                      className="rounded border px-2 py-0.5 disabled:opacity-50"
                      disabled={busy}
                      onClick={() => act(`retry ${d.job_id}`, () => retryOpsDlq(d.id))}
                    >
                      retry
                    </button>
                    <button
                      className="rounded border px-2 py-0.5 disabled:opacity-50"
                      disabled={busy}
                      onClick={() => act(`resolve ${d.job_id}`, () => resolveOpsDlq(d.id))}
                    >
                      resolve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-xs text-success">DLQ 비어 있음</p>
        )}
      </Card>

      <Card title="백업">
        {backups ? (
          <pre className="max-h-72 overflow-auto rounded-lg bg-surface-2 p-3 text-xs">
            {JSON.stringify(backups, null, 2)}
          </pre>
        ) : (
          <p className="text-xs text-subtle">loading…</p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="rounded-lg border px-3 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={() =>
              act("run full backup", () => runOpsBackup("full"), "Run a full pg_dump backup now?")
            }
          >
            Run full backup
          </button>
          <button
            className="rounded-lg border px-3 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={() =>
              act("run storage backup", () => runOpsBackup("storage"), "Run a storage (assets) backup now?")
            }
          >
            Run storage backup
          </button>
          <button
            className="rounded-lg border px-3 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={() => {
              const id = window.prompt("Backup id to verify?");
              if (id) act(`verify ${id}`, () => verifyOpsBackup(id));
            }}
          >
            Verify backup by id
          </button>
        </div>
      </Card>

      <Card title="무결성 · 비용 점검">
        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-lg border px-3 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={() => act("cost anomaly check", checkCostAnomaly)}
          >
            Check cost anomaly
          </button>
          <button
            className="rounded-lg border px-3 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={() => act("storage integrity scan", scanStorageIntegrity)}
          >
            Scan storage integrity
          </button>
        </div>
      </Card>
    </div>
  );
}

function FlagRow({
  name,
  on,
  busy,
  locked,
  hint,
  onToggle,
}: {
  name: string;
  on: boolean;
  busy?: boolean;
  locked?: boolean;
  hint?: string;
  onToggle?: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-40 font-mono">{name}</span>
      <Dot status={on ? "WARNING" : "OK"} />
      <span className="text-ink-subtle">{on ? "ENABLED" : "disabled"}</span>
      {locked ? (
        <span className="ml-auto text-[11px] text-ink-tertiary">{hint}</span>
      ) : (
        <button
          className="ml-auto rounded border px-2 py-0.5 disabled:opacity-50"
          disabled={busy}
          onClick={() => onToggle?.(!on)}
        >
          {on ? "disable" : "enable"}
        </button>
      )}
    </div>
  );
}
