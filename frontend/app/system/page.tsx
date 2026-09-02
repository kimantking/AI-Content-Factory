"use client";

import { useEffect, useState } from "react";
import { getOpsStatus, localAIStatus } from "@/lib/api";

function Row({ name, ok, detail }: { name: string; ok: boolean | null; detail?: string }) {
  const label = ok === null ? "확인 불가" : ok ? "정상" : "문제";
  const color = ok === null ? "bg-surface-3" : ok ? "bg-success" : "bg-brand-secure";
  return (
    <div className="flex items-center gap-2 border-b border-hairline py-2 text-sm">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
      <span className="font-medium">{name}</span>
      <span className="text-xs text-ink-subtle">{label}{detail ? ` · ${detail}` : ""}</span>
    </div>
  );
}

export default function SystemStatus() {
  const [ops, setOps] = useState<Record<string, any> | null>(null);
  const [local, setLocal] = useState<Record<string, any> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getOpsStatus().then((r) => setOps(r as Record<string, any>)).catch((e) => setErr(String(e)));
    localAIStatus().then((r) => setLocal(r as Record<string, any>)).catch(() => setLocal({ status: "NOT_RUNNING" }));
  }, []);

  const allOk = ops && local && ops.database !== false && String(local.status) !== "NOT_RUNNING";

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">시스템</h1>
      <div className="rounded-lg border border-hairline bg-surface-1 p-5">
        <div className="mb-2 text-lg font-bold">
          {allOk ? "✅ 시스템 정상" : "⚠️ 일부 구성 요소 확인 필요"}
        </div>
        {err && <p className="text-sm text-brand-secure">{err}</p>}
        <Row name="Backend API" ok={ops != null} />
        <Row name="Database" ok={ops ? ops.database ?? ops.db ?? true : null} />
        <Row name="Redis / Queue" ok={ops ? ops.redis ?? ops.queue ?? null : null} />
        <Row name="Workers" ok={ops ? (ops.workers?.length ?? 0) > 0 || ops.run_inline : null}
          detail={ops?.run_inline ? "inline 모드" : undefined} />
        <Row name="Local AI (Ollama)" ok={local ? String(local.status) === "CONNECTED" : null}
          detail={local ? String(local.status) : undefined} />
        <Row name="Cloud Providers" ok={ops ? ops.cloud_ready ?? null : null}
          detail="키 미설정 시 MOCK / 로컬 사용" />
        <Row name="Storage" ok={ops ? ops.storage ?? true : null} />
        <Row name="Publishers" ok={true} detail="MOCK (자격증명 미제공)" />
      </div>
      <p className="text-xs text-ink-tertiary">
        상태는 색과 함께 “정상 / 문제 / 확인 불가” 텍스트로 표시됩니다.
      </p>
    </div>
  );
}
