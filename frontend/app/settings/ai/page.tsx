"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ProviderRow,
  ProviderVoice,
  deleteProviderKey,
  elevenlabsVoices,
  listProviders,
  setElevenlabsVoice,
  setProviderKey,
  testProvider,
} from "@/lib/api";

/* 상태 → 한국어 라벨 + 톤. 색 단독 금지 — 항상 텍스트 라벨 동반. */
const STATUS_KO: Record<string, { label: string; tone: string }> = {
  NOT_CONFIGURED: { label: "연결 필요", tone: "text-ink-subtle" },
  CONFIGURED: { label: "설정됨", tone: "text-brand-secure" },
  CHECKING: { label: "연결 확인 중", tone: "text-brand-secure" },
  CONNECTED: { label: "연결됨", tone: "text-success" },
  AUTH_FAILED: { label: "인증 실패", tone: "text-brand-secure" },
  RATE_LIMITED: { label: "요청 한도 초과", tone: "text-brand-secure" },
  BILLING: { label: "결제 확인 필요", tone: "text-brand-secure" },
  QUOTA: { label: "쿼터 초과", tone: "text-brand-secure" },
  MODEL_UNAVAILABLE: { label: "모델 사용 불가", tone: "text-brand-secure" },
  NEEDS_WORKSPACE_ID: { label: "워크스페이스 ID 필요", tone: "text-brand-secure" },
  BLOCKED: { label: "차단됨 (유료 일시중지)", tone: "text-brand-secure" },
  DEGRADED: { label: "부분 동작", tone: "text-brand-secure" },
  DISABLED: { label: "비활성", tone: "text-ink-subtle" },
  ERROR: { label: "오류", tone: "text-brand-secure" },
};

const PROVIDER_KO: Record<string, { name: string; role: string; keyHint: string }> = {
  anthropic: { name: "Anthropic", role: "클라우드 LLM (대본·전략·검수)", keyHint: "sk-ant-..." },
  tavily: { name: "Tavily", role: "웹 검색 (리서치)", keyHint: "tvly-..." },
  google: { name: "Google AI", role: "이미지·영상 (Imagen / Veo)", keyHint: "AIza..." },
  elevenlabs: { name: "ElevenLabs", role: "음성 / TTS", keyHint: "sk_..." },
  ollama: { name: "Ollama", role: "로컬 LLM (gemma3:4b)", keyHint: "" },
};

const ORDER = ["anthropic", "tavily", "google", "elevenlabs", "ollama"];

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_KO[status] ?? { label: status, tone: "text-ink-subtle" };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded bg-surface-2 px-2 py-0.5 text-xs ${s.tone}`}>
      <span aria-hidden className="text-[10px]">●</span>
      {s.label}
    </span>
  );
}

export default function AIConnectionsPage() {
  const [rows, setRows] = useState<ProviderRow[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string>("");
  const [probe, setProbe] = useState<Record<string, Record<string, unknown>>>({});
  const [voices, setVoices] = useState<ProviderVoice[]>([]);
  const [voiceId, setVoiceId] = useState<string>("");
  const [msg, setMsg] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const r = await listProviders(false);
      setRows(r.providers);
    } catch (e) {
      setMsg(`목록 로드 실패: ${String(e)}`);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const row = (p: string) => rows.find((x) => x.provider === p);

  const saveKey = async (p: string) => {
    const key = (draft[p] ?? "").trim();
    if (key.length < 8) {
      setMsg("API 키가 너무 짧습니다.");
      return;
    }
    setBusy(`save:${p}`);
    setMsg("");
    try {
      await setProviderKey(p, key);
      setDraft({ ...draft, [p]: "" });
      setEditing({ ...editing, [p]: false });
      await load();
    } catch (e) {
      setMsg(`저장 실패 (${p}): ${String(e)}`);
    } finally {
      setBusy("");
    }
  };

  const disconnect = async (p: string) => {
    setBusy(`del:${p}`);
    setMsg("");
    try {
      await deleteProviderKey(p);
      setProbe({ ...probe, [p]: {} });
      await load();
    } catch (e) {
      setMsg(`연결 해제 실패 (${p}): ${String(e)}`);
    } finally {
      setBusy("");
    }
  };

  const runTest = async (p: string) => {
    setBusy(`test:${p}`);
    setMsg("");
    setRows((rs) => rs.map((r) => (r.provider === p ? { ...r, status: "CHECKING" } : r)));
    try {
      const res = await testProvider(p);
      setProbe({ ...probe, [p]: res });
      if (p === "elevenlabs" && res.ok) {
        try {
          const v = await elevenlabsVoices();
          setVoices(v.voices ?? []);
          setVoiceId(v.voice_id ?? "");
        } catch {
          /* ignore */
        }
      }
      await load();
    } catch (e) {
      setMsg(`연결 확인 실패 (${p}): ${String(e)}`);
      await load();
    } finally {
      setBusy("");
    }
  };

  const chooseVoice = async (id: string) => {
    setVoiceId(id);
    setBusy("voice");
    try {
      await setElevenlabsVoice(id);
      await load();
    } catch (e) {
      setMsg(`목소리 저장 실패: ${String(e)}`);
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">AI 연결</h1>
        <p className="mt-1 text-xs text-ink-subtle">
          발급받은 API 키를 여기에 입력하세요. 키는 서버에서 암호화되어 저장되며 화면·로그에 다시 표시되지 않습니다.
          연결 확인을 통과한 공급자는 실전 모드에서 실제 콘텐츠 제작에 사용됩니다. API 키는 백엔드에만 보관됩니다.
        </p>
        <p className="mt-1 text-[11px] text-ink-tertiary">권장 순서: Ollama → Tavily → Google AI → ElevenLabs (Anthropic은 선택)</p>
      </div>

      {msg && <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-brand-secure">{msg}</div>}

      {ORDER.map((p) => {
        const r = row(p);
        const meta = PROVIDER_KO[p];
        const pr = probe[p] ?? {};
        const isCloud = p !== "ollama";
        const configured = Boolean(r?.configured);
        const showInput = !configured || editing[p];
        return (
          <section key={p} className="rounded-lg border border-hairline bg-surface-1 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-bold">{meta.name}</h2>
              <StatusBadge status={r?.status ?? "NOT_CONFIGURED"} />
              {r?.key_source && r.key_source !== "none" && (
                <span className="text-[11px] text-ink-tertiary">
                  키 출처: {r.key_source === "env" ? ".env" : r.key_source === "workspace" ? "워크스페이스" : "인스턴스"}
                </span>
              )}
              {r?.last4 && <span className="text-[11px] text-ink-tertiary">••••{r.last4}</span>}
            </div>
            <p className="mt-0.5 text-xs text-ink-subtle">{meta.role}</p>

            {isCloud ? (
              <>
                {showInput ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <input
                      type="password"
                      autoComplete="off"
                      spellCheck={false}
                      className="input !w-72 !py-1 text-xs"
                      placeholder={meta.keyHint || "API 키"}
                      value={draft[p] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [p]: e.target.value })}
                    />
                    <button
                      className="input !w-auto !py-1 text-xs"
                      disabled={busy === `save:${p}`}
                      onClick={() => saveKey(p)}
                    >
                      {busy === `save:${p}` ? "저장 중…" : "저장"}
                    </button>
                    {configured && (
                      <button
                        className="input !w-auto !py-1 text-xs"
                        onClick={() => setEditing({ ...editing, [p]: false })}
                      >
                        취소
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      className="input !w-auto !py-1 text-xs"
                      disabled={busy === `test:${p}`}
                      onClick={() => runTest(p)}
                    >
                      {busy === `test:${p}` ? "확인 중…" : "연결 확인"}
                    </button>
                    <button
                      className="input !w-auto !py-1 text-xs"
                      onClick={() => setEditing({ ...editing, [p]: true })}
                    >
                      키 변경
                    </button>
                    <button
                      className="input !w-auto !py-1 text-xs"
                      disabled={busy === `del:${p}`}
                      onClick={() => disconnect(p)}
                    >
                      연결 해제
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  className="input !w-auto !py-1 text-xs"
                  disabled={busy === `test:${p}`}
                  onClick={() => runTest(p)}
                >
                  {busy === `test:${p}` ? "확인 중…" : "연결 확인"}
                </button>
              </div>
            )}

            {/* probe detail / capabilities */}
            {Boolean(pr.detail) && (
              <p className="mt-2 text-[11px] text-ink-tertiary">{String(pr.detail)}</p>
            )}
            {p === "google" && Boolean(pr.image_capability || pr.video_capability) && (
              <div className="mt-2 text-[11px] text-ink-subtle">
                이미지 {pr.image_capability === "OK" ? "모델 확인됨" : "모델 확인 필요"} · 영상{" "}
                {pr.video_capability === "OK" ? "모델 확인됨" : "모델 확인 필요"}
                <span className="text-ink-tertiary">
                  {" "}
                  ({String(pr.image_model ?? "")} / {String(pr.video_model ?? "")})
                </span>
              </div>
            )}
            {p === "elevenlabs" && (r?.status === "CONNECTED" || Boolean(pr.ok)) && (
              <div className="mt-2 text-xs">
                <label className="text-[11px] text-ink-subtle">기본 목소리</label>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <select
                    className="input !w-64 !py-1 text-xs"
                    value={voiceId}
                    disabled={busy === "voice"}
                    onChange={(e) => chooseVoice(e.target.value)}
                  >
                    <option value="">목소리 선택 필요</option>
                    {(voices.length
                      ? voices
                      : ((r?.meta?.voices as ProviderVoice[]) ?? [])
                    ).map((v) => (
                      <option key={v.voice_id} value={v.voice_id}>
                        {v.name}
                        {v.labels?.language ? ` · ${v.labels.language}` : ""}
                      </option>
                    ))}
                  </select>
                  {!voiceId && (
                    <span className="text-[11px] text-brand-secure">TTS: 목소리 선택 필요</span>
                  )}
                </div>
              </div>
            )}
          </section>
        );
      })}

      <p className="text-[11px] text-ink-tertiary">
        연결 상태는 <a className="underline" href="/support">AI 지원</a> 스냅샷과 대시보드에 반영됩니다.
      </p>
    </div>
  );
}
