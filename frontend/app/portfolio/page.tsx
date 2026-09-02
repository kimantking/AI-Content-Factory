"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BrandRow,
  ChannelRow,
  PortfolioView,
  WorkspaceRow,
  allocatePortfolioBudget,
  getChannelMonetization,
  getPortfolio,
  getPortfolioRecs,
  listBrands,
  listChannels,
  listWorkspaces,
} from "@/lib/api";

function Card({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-hairline bg-surface-1 p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-bold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

const num = (v: unknown) => (typeof v === "number" ? Math.round(v * 10) / 10 : "—");

export default function PortfolioPage() {
  const [apiKey, setApiKey] = useState("");
  const [wsId, setWsId] = useState("");
  const [workspaces, setWorkspaces] = useState<WorkspaceRow[]>([]);
  const [brands, setBrands] = useState<BrandRow[]>([]);
  const [channels, setChannels] = useState<ChannelRow[]>([]);
  const [pf, setPf] = useState<PortfolioView | null>(null);
  const [recs, setRecs] = useState<Record<string, unknown>[]>([]);
  const [alloc, setAlloc] = useState<Record<string, unknown> | null>(null);
  const [mon, setMon] = useState<Record<string, Record<string, unknown>>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    try {
      setApiKey(window.localStorage.getItem("acf_api_key") ?? "");
      setWsId(window.localStorage.getItem("acf_workspace_id") ?? "");
    } catch {
      /* ignore */
    }
  }, []);

  const saveCreds = () => {
    try {
      window.localStorage.setItem("acf_api_key", apiKey);
      window.localStorage.setItem("acf_workspace_id", wsId);
    } catch {
      /* ignore */
    }
    load();
  };

  const load = useCallback(async () => {
    setErr(null);
    try {
      const ws = await listWorkspaces();
      setWorkspaces(ws);
      const active = wsId || ws[0]?.id || "";
      if (!wsId && active) setWsId(active);
      if (!active) return;
      const [b, c, p, r] = await Promise.all([
        listBrands(active),
        listChannels(`?workspace_id=${active}`),
        getPortfolio(active),
        getPortfolioRecs(active),
      ]);
      setBrands(b);
      setChannels(c);
      setPf(p);
      setRecs(r);
    } catch (e) {
      setErr(String(e));
    }
  }, [wsId]);

  useEffect(() => {
    load();
  }, [load]);

  const runAlloc = async (objective: string) => {
    try {
      setAlloc(await allocatePortfolioBudget(wsId, objective));
    } catch (e) {
      setErr(String(e));
    }
  };

  const loadMon = async (id: string) => {
    try {
      setMon((m) => ({ ...m, [id]: {} }));
      const r = await getChannelMonetization(id);
      setMon((m) => ({ ...m, [id]: r }));
    } catch (e) {
      setErr(String(e));
    }
  };

  const totals = (pf?.totals ?? {}) as Record<string, unknown>;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-3">
        <h1 className="text-lg font-bold">채널 · 포트폴리오</h1>
        <button className="ml-auto rounded-lg border px-3 py-1 text-xs" onClick={load}>
          refresh
        </button>
      </div>
      {err && <p className="rounded-lg bg-surface-2 p-3 text-xs text-brand-secure">{err}</p>}

      <Card title="연결 상태">
        <div className="flex flex-wrap items-end gap-3 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-ink-subtle">API key (X-Api-Key)</span>
            <input
              className="w-72 rounded border px-2 py-1 font-mono"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="acf_..."
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-ink-subtle">작업공간</span>
            <select className="input !w-auto !py-1" value={wsId} onChange={(e) => setWsId(e.target.value)}>
              <option value="">(pick)</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} — {w.role ?? "?"}
                </option>
              ))}
            </select>
          </label>
          <button className="rounded-lg bg-primary px-3 py-1.5 text-on-primary" onClick={saveCreds}>
            save + load
          </button>
          <span className="text-ink-tertiary">
            stored per-browser; auth is only enforced by the API in production
          </span>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-4">
        {([
          ["Channels", totals["channels"]],
          ["Active", totals["active"]],
          ["Σ daily budget $", totals["sum_daily_budget_usd"]],
          ["Avg health", totals["avg_health"]],
        ] as [string, unknown][]).map(([k, v]) => (
          <div key={k} className="rounded-lg border border-hairline bg-surface-1 p-4 text-center">
            <div className="text-xs text-ink-subtle">{k}</div>
            <div className="text-xl font-bold">{num(v)}</div>
          </div>
        ))}
      </div>

      <Card title={`Brands (${brands.length})`}>
        <div className="flex flex-wrap gap-2 text-xs">
          {brands.map((b) => (
            <span key={b.id} className="rounded-full border px-3 py-1">
              {b.name} · {b.status} · {b.channels} ch
            </span>
          ))}
          {brands.length === 0 && <span className="text-ink-tertiary">브랜드 없음</span>}
        </div>
      </Card>

      <Card
        title={`Channel portfolio · objective ${pf?.objective ?? "—"}`}
        right={
          <span className="flex gap-1 text-xs">
            {["GROWTH", "REVENUE", "PROFIT", "BALANCED"].map((o) => (
              <button key={o} className="rounded border px-2 py-0.5" onClick={() => runAlloc(o)}>
                allocate {o}
              </button>
            ))}
          </span>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-tertiary">
                <th className="py-1 pr-2">채널</th>
                <th className="py-1 pr-2">플랫폼</th>
                <th className="py-1 pr-2">상태</th>
                <th className="py-1 pr-2">상태</th>
                <th className="py-1 pr-2">포트폴리오</th>
                <th className="py-1 pr-2">성장률</th>
                <th className="py-1 pr-2">수익</th>
                <th className="py-1 pr-2">순이익</th>
                <th className="py-1 pr-2">규모</th>
                <th className="py-1 pr-2">alloc $</th>
                <th className="py-1"></th>
              </tr>
            </thead>
            <tbody>
              {channels.map((c) => {
                const s = (pf?.channels?.[c.id] ?? {}) as Record<string, unknown>;
                const a = (alloc?.allocations as Record<string, number> | undefined)?.[c.id];
                return (
                  <tr key={c.id} className="border-b border-hairline last:border-0">
                    <td className="py-1 pr-2 font-medium">{c.name}</td>
                    <td className="py-1 pr-2">{c.platform}</td>
                    <td className="py-1 pr-2">{c.status}/{c.lifecycle}</td>
                    <td className="py-1 pr-2">{num(s["health_score"])}</td>
                    <td className="py-1 pr-2 font-semibold">{num(s["portfolio_score"])}</td>
                    <td className="py-1 pr-2">{num(s["growth_score"])}</td>
                    <td className="py-1 pr-2">{num(s["revenue_score"])}</td>
                    <td className="py-1 pr-2">{num(s["profit_score"])}</td>
                    <td className="py-1 pr-2">{String(s["scale_status"] ?? "—")}</td>
                    <td className="py-1 pr-2 tabular-nums">{a != null ? a.toFixed(0) : "—"}</td>
                    <td className="py-1">
                      <button className="rounded border px-2 py-0.5" onClick={() => loadMon(c.id)}>
                        $ model
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {alloc && (
          <p className="mt-2 text-xs text-ink-subtle">
            total ${num(alloc["total_usd"])} · trend reserve ${num(alloc["trend_reserve_usd"])} ·
            floor ${num(alloc["min_exploration_floor_usd"])} · hard-capped {String(alloc["hard_capped"])}
          </p>
        )}
      </Card>

      {Object.keys(mon).length > 0 && (
        <Card title="채널별 수익 모델 적합도">
          {Object.entries(mon).map(([id, m]) => {
            const ch = channels.find((c) => c.id === id);
            const fit = (m["model_fit"] as Record<string, number>) ?? {};
            const pc = (m["profit_center"] as Record<string, unknown>) ?? {};
            return (
              <div key={id} className="mb-3 border-b border-hairline pb-2 text-xs last:border-0">
                <div className="font-semibold">
                  {ch?.name} → recommended: {String(m["recommended_primary_model"] ?? "…")}
                </div>
                <div className="flex flex-wrap gap-2 py-1">
                  {Object.entries(fit).map(([k, v]) => (
                    <span key={k} className="rounded bg-surface-2 px-2 py-0.5">
                      {k}:{v}
                    </span>
                  ))}
                </div>
                <div className="text-ink-subtle">
                  actual ${num(pc["revenue_actual_usd"])} · est ${num(pc["revenue_estimated_usd"])} (separate) ·
                  cost ${num(pc["production_cost_usd"])} · net ${num(pc["net_profit_usd"])}
                </div>
              </div>
            );
          })}
        </Card>
      )}

      <Card title={`Portfolio recommendations (${recs.length}) — advisory, never auto-applied`}>
        <table className="w-full text-xs">
          <tbody>
            {recs.map((r, i) => (
              <tr key={i} className="border-b border-hairline last:border-0">
                <td className="py-1 pr-2 font-mono">{String(r["action"])}</td>
                <td className="py-1 pr-2 text-ink-subtle">
                  {channels.find((c) => c.id === r["channel_id"])?.name ?? String(r["channel_id"] ?? "")}
                </td>
                <td className="py-1 pr-2">conf {num(r["confidence"])}</td>
                <td className="py-1 pr-2">n={String(r["sample_size"])}</td>
                <td className="py-1 text-ink-subtle">{JSON.stringify(r["detail"])}</td>
              </tr>
            ))}
            {recs.length === 0 && (
              <tr>
                <td className="py-1 text-ink-tertiary">추천 없음</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
