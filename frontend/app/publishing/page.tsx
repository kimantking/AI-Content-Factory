"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AccountRow,
  PlatformCapabilityRow,
  disconnectAccount,
  getCapabilities,
  listAccounts,
  mockConnect,
  startConnect,
} from "@/lib/api";

const BADGE: Record<string, string> = {
  CONNECTED: "bg-surface-2 text-success",
  TOKEN_EXPIRING: "bg-surface-2 text-brand-secure",
  REFRESH_REQUIRED: "bg-surface-2 text-brand-secure",
  REAUTH_REQUIRED: "bg-surface-2 text-brand-secure",
  PERMISSION_MISSING: "bg-surface-2 text-brand-secure",
  DISCONNECTED: "bg-surface-2 text-ink-subtle",
  SUPPORTED: "bg-surface-2 text-success",
  AUTH_REQUIRED: "bg-surface-2 text-primary",
  APP_REVIEW_REQUIRED: "bg-surface-2 text-brand-secure",
  ACCOUNT_TYPE_REQUIRED: "bg-surface-2 text-brand-secure",
  LIMITED: "bg-surface-2 text-primary",
  MANUAL_ONLY: "bg-surface-3 text-ink-muted",
  NOT_SUPPORTED: "bg-surface-2 text-brand-secure",
};
const Badge = ({ s }: { s: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[s] ?? BADGE.DISCONNECTED}`}>{s}</span>
);

export default function PublishingAccounts() {
  const [caps, setCaps] = useState<PlatformCapabilityRow[]>([]);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, a] = await Promise.all([getCapabilities(), listAccounts()]);
      setCaps(c);
      setAccounts(a);
    } catch (e) {
      setErr(String(e));
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const byPlatform = new Map(accounts.map((a) => [a.platform, a]));

  async function onConnect(platform: string) {
    setBusy(true);
    try {
      const r = await startConnect(platform);
      if (r.mode === "REAL" && r.authorization_url) window.open(r.authorization_url, "_blank");
      else await mockConnect(platform);
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">게시 · 계정 연결</h1>
        <a href="/" className="text-sm text-primary underline">
          ← 대시보드
        </a>
      </div>
      {err && <p className="text-sm text-brand-secure">{err}</p>}

      <div className="space-y-2">
        {caps.map((c) => {
          const acct = byPlatform.get(c.platform);
          return (
            <section key={c.platform} className="rounded-md border border-hairline bg-surface-1 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{c.platform}</span>
                <Badge s={c.publishing_status} />
                <span className="text-xs text-subtle">{c.implementation_status}</span>
                {c.app_review_required && <Badge s="APP_REVIEW_REQUIRED" />}
                <span className="ml-auto">
                  {acct ? <Badge s={acct.connection_status} /> : <Badge s="DISCONNECTED" />}
                </span>
              </div>
              <p className="mt-1 text-xs text-subtle">{c.official_api}</p>
              <p className="mt-1 text-xs text-subtle">요구: {c.account_requirement}</p>
              <p className="mt-1 text-[11px] text-ink-tertiary">{c.known_limits}</p>
              <div className="mt-2 flex gap-2">
                {!acct || acct.connection_status === "DISCONNECTED" ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onConnect(c.platform)}
                    className="rounded border border-hairline px-3 py-1 text-xs disabled:opacity-40"
                  >
                    Connect
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onConnect(c.platform)}
                      className="rounded border border-hairline px-3 py-1 text-xs"
                    >
                      Reconnect
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        await disconnectAccount(acct.id);
                        load();
                      }}
                      className="rounded border border-hairline px-3 py-1 text-xs"
                    >
                      Disconnect
                    </button>
                  </>
                )}
                <span className="text-[11px] text-ink-tertiary self-center">
                  verified {c.last_verified_at}
                </span>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
