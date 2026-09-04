"use client";

import { useCallback, useEffect, useState } from "react";
import { finishSetup, localAIPing, localAIStatus, listWorkspaces } from "@/lib/api";

const STEPS = [
  "워크스페이스", "브랜드", "SNS 계정", "AI 제공자", "로컬 AI",
  "스타일", "예산 / 안전", "테스트 실행",
] as const;
const KEY = "acf_setup_wizard";

type State = {
  step: number;
  workspace: string;
  brand: string;
  concept: string;
  topics: string;
  sns: string[];
  cloudKey: boolean;
  localChecked: boolean;
  style: string;
  budget: number;
  dryRunOk: boolean;
};
const INIT: State = {
  step: 0, workspace: "", brand: "", concept: "", topics: "", sns: ["youtube_shorts"], cloudKey: false,
  localChecked: false, style: "균형", budget: 2, dryRunOk: false,
};

export default function SetupWizard() {
  const [s, setS] = useState<State>(INIT);
  const [local, setLocal] = useState<Record<string, unknown> | null>(null);
  const [ping, setPing] = useState<Record<string, unknown> | null>(null);
  const [wsList, setWsList] = useState<{ name: string }[]>([]);

  useEffect(() => {
    try {
      const raw = window.localStorage?.getItem(KEY);
      if (raw) setS({ ...INIT, ...JSON.parse(raw) });
    } catch { /* ignore */ }
    listWorkspaces().then(setWsList).catch(() => undefined);
  }, []);
  const persist = useCallback((next: State) => {
    setS(next);
    try { window.localStorage?.setItem(KEY, JSON.stringify(next)); } catch { /* ignore */ }
  }, []);

  const set = (patch: Partial<State>) => persist({ ...s, ...patch });
  const next = () => set({ step: Math.min(s.step + 1, STEPS.length - 1) });
  const prev = () => set({ step: Math.max(s.step - 1, 0) });

  const checkLocal = async () => {
    const st = await localAIStatus().catch((e) => ({ status: "NOT_RUNNING", reason: String(e) }));
    setLocal(st as Record<string, unknown>);
    set({ localChecked: true });
  };

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const finish = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await finishSetup({
        workspace: s.workspace,
        brand: s.brand,
        sns: s.sns,
        concept: s.concept,
        topics: s.topics.split(",").map((item) => item.trim()).filter(Boolean),
      });
      try {
        if (res.workspace_id) window.localStorage?.setItem("acf_workspace_id", res.workspace_id);
        window.localStorage?.setItem(KEY, JSON.stringify({
          ...s, workspaceId: res.workspace_id, brandId: res.brand_id,
        }));
      } catch { /* ignore */ }
      setSaveMsg(res.created.length ? `저장됨: ${res.created.join(", ")}` : "기존 설정을 사용합니다");
      window.location.href = "/create";
    } catch (e) {
      setSaveMsg(`저장 실패: ${String(e)} — 로컬에는 저장되어 있습니다`);
    } finally {
      setSaving(false);
    }
  };

  const canContinue = s.step !== 0 || Boolean(s.workspace.trim());
  const canLeaveBrand = s.step !== 1 || Boolean(s.brand.trim() && s.concept.trim() && s.topics.trim());
  const canLeaveSns = s.step !== 2 || s.sns.length > 0;

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">초기 설정</h1>
      <ol className="flex flex-wrap gap-1 text-[11px]">
        {STEPS.map((label, i) => (
          <li key={label}
            className={`rounded px-2 py-1 ${i === s.step ? "bg-primary text-on-primary"
              : i < s.step ? "bg-surface-2 text-success" : "bg-surface-2 text-ink-subtle"}`}>
            {i + 1}. {label}
          </li>
        ))}
      </ol>
      <p className="text-xs text-ink-subtle">진행 상황은 자동 저장됩니다. 나중에 이어서 할 수 있습니다.</p>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        {s.step === 0 && (
          <div>
            <label className="text-sm font-bold">워크스페이스 이름</label>
            <input className="mt-2 w-full rounded border border-hairline px-3 py-2"
              value={s.workspace} onChange={(e) => set({ workspace: e.target.value })}
              placeholder="예: 우리 스튜디오" />
            {wsList.length > 0 && (
              <p className="mt-1 text-xs text-ink-subtle">기존: {wsList.map((w) => w.name).join(", ")}</p>
            )}
          </div>
        )}
        {s.step === 1 && (
          <div className="space-y-3">
            <label className="text-sm font-bold">첫 브랜드</label>
            <input className="mt-2 w-full rounded border border-hairline px-3 py-2"
              value={s.brand} onChange={(e) => set({ brand: e.target.value })}
              placeholder="예: 테크 채널" />
            <label className="block text-sm font-bold">채널 콘셉트</label>
            <textarea className="h-20 w-full rounded border border-hairline px-3 py-2"
              value={s.concept} onChange={(e) => set({ concept: e.target.value })}
              placeholder="예: 초보자에게 AI 도구와 자동화 방법을 쉽게 알려주는 채널" />
            <label className="block text-sm font-bold">업로드할 주제</label>
            <input className="w-full rounded border border-hairline px-3 py-2"
              value={s.topics} onChange={(e) => set({ topics: e.target.value })}
              placeholder="예: AI 도구, 업무 자동화, 콘텐츠 제작 (쉼표로 구분)" />
            <p className="text-xs text-ink-subtle">선택한 모든 SNS에 우선 동일하게 적용하며 나중에 채널별로 수정할 수 있습니다.</p>
          </div>
        )}
        {s.step === 2 && (
          <div>
            <div className="text-sm font-bold">게시할 SNS</div>
            <div className="mt-2 flex flex-wrap gap-2 text-sm">
              {["youtube_shorts", "tiktok", "instagram_reel", "x", "threads", "linkedin", "naver_blog"].map((p) => (
                <label key={p} className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={s.sns.includes(p)}
                    onChange={(e) => set({ sns: e.target.checked ? [...s.sns, p] : s.sns.filter((x) => x !== p) })} />
                  {p}
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-ink-subtle">계정 연결은 이후 “계정” 화면에서 진행합니다. 지금은 선택만.</p>
          </div>
        )}
        {s.step === 3 && (
          <div className="text-sm">
            <div className="font-bold">클라우드 AI (선택)</div>
            <label className="mt-2 inline-flex items-center gap-1">
              <input type="checkbox" checked={s.cloudKey} onChange={(e) => set({ cloudKey: e.target.checked })} />
              Anthropic API 키를 .env에 설정했습니다
            </label>
            <p className="mt-1 text-xs text-ink-subtle">키가 없어도 로컬 AI로 대부분 기능을 사용할 수 있습니다.</p>
          </div>
        )}
        {s.step === 4 && (
          <div className="text-sm">
            <div className="font-bold">로컬 AI (Ollama)</div>
            <button className="mt-2 rounded bg-primary px-3 py-1.5 text-on-primary" onClick={checkLocal}>연결 확인</button>
            {local && (
              <div className="mt-2 rounded border border-hairline p-2 text-xs">
                상태: <b>{String(local.status)}</b>{" "}
                {Array.isArray(local.models) && ` · 모델: ${(local.models as string[]).join(", ") || "없음"}`}
                {local.reason ? <div className="text-brand-secure">{String(local.reason)}</div> : null}
                <button className="ml-2 rounded border px-2 py-0.5"
                  onClick={async () => setPing(await localAIPing().catch((e) => ({ ok: false, error: String(e) })))}>
                  간단 추론 테스트
                </button>
                {ping && <div className="mt-1">{ping.ok ? `OK: ${String(ping.sample)}` : `실패: ${String(ping.error)}`}</div>}
              </div>
            )}
            <p className="mt-1 text-xs text-ink-subtle">모델(수 GB)은 사용자 승인 없이 자동 다운로드하지 않습니다.</p>
          </div>
        )}
        {s.step === 5 && (
          <div className="text-sm">
            <div className="font-bold">기본 품질</div>
            <div className="mt-2 flex gap-3">
              {["빠르게", "균형", "고품질", "최고품질"].map((q) => (
                <label key={q} className="inline-flex items-center gap-1">
                  <input type="radio" name="style" checked={s.style === q} onChange={() => set({ style: q })} />{q}
                </label>
              ))}
            </div>
          </div>
        )}
        {s.step === 6 && (
          <div className="text-sm">
            <label className="font-bold">캠페인당 예산 (USD)</label>
            <input type="number" min={0} step={0.5} className="mt-2 w-28 rounded border border-hairline px-2 py-1"
              value={s.budget} onChange={(e) => set({ budget: Number(e.target.value) })} />
            <p className="mt-1 text-xs text-ink-subtle">예산 근접 시 로컬/캐시 사용이 늘고 후보 수가 줄어듭니다. 사실검증·검수·보안은 우회하지 않습니다.</p>
          </div>
        )}
        {s.step === 7 && (
          <div className="text-sm">
            <div className="font-bold">안전 테스트 실행</div>
            <p className="mt-1 text-xs text-ink-subtle">실제 게시 없이 파이프라인을 한 번 돌려봅니다.</p>
            <label className="mt-2 inline-flex items-center gap-1">
              <input type="checkbox" checked={s.dryRunOk} onChange={(e) => set({ dryRunOk: e.target.checked })} />
              테스트 실행을 확인했습니다
            </label>
          </div>
        )}
      </section>

      <div className="flex gap-2">
        <button className="rounded border px-4 py-2 text-sm disabled:opacity-40"
          disabled={s.step === 0} onClick={prev}>이전</button>
        {s.step < STEPS.length - 1 ? (
          <button className="rounded bg-primary px-4 py-2 text-sm text-on-primary disabled:opacity-40"
            disabled={!canContinue || !canLeaveBrand || !canLeaveSns} onClick={next}>다음</button>
        ) : (
          <button className="rounded bg-success px-4 py-2 text-sm font-bold text-on-primary disabled:opacity-50"
            disabled={saving} onClick={finish}>
            {saving ? "저장 중…" : "설정 완료 · 만들기 시작"}
          </button>
        )}
        {saveMsg && <span className="self-center text-xs text-ink-subtle">{saveMsg}</span>}
        <button className="ml-auto text-xs text-ink-tertiary underline"
          onClick={() => { try { window.localStorage?.removeItem(KEY); } catch { /* */ } persist(INIT); }}>
          초기화
        </button>
      </div>
    </div>
  );
}
