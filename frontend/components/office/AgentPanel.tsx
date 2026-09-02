"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { AGENTS, STATE_META, type AgentId, type OfficeModel } from "./office-data";
import { Icon } from "@/components/ui/Icon";
import { chatWithAgent, type AgentChatMessage } from "@/lib/api";

function fmtElapsed(s: number | null) {
  if (s == null) return "-";
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}분 ${Math.round(s % 60)}초` : `${Math.round(s)}초`;
}

export function AgentPanel({
  id,
  model,
  onClose,
}: {
  id: AgentId;
  model: OfficeModel;
  onClose: () => void;
}) {
  const agent = AGENTS.find((a) => a.id === id)!;
  const st = model.stations[id];
  const m = STATE_META[st];
  const j = model.job;
  const working = st === "RUNNING";
  const campaignHref = j.campaignId ? `/campaigns/${j.campaignId}` : null;
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([{ role: "assistant", content: `안녕하세요. ${agent.role}입니다. 무엇을 도와드릴까요?` }]);
    setDraft("");
    setChatError("");
  }, [id, agent.role]);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  async function sendMessage(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    const next = [...messages, { role: "user", content: text } as AgentChatMessage];
    setMessages(next);
    setDraft("");
    setSending(true);
    setChatError("");
    try {
      const result = await chatWithAgent(id, text, next.slice(0, -1));
      setMessages((rows) => [...rows, { role: "assistant", content: result.reply }]);
    } catch {
      setChatError("AI와 연결하지 못했습니다. 백엔드와 AI 설정을 확인해 주세요.");
    } finally {
      setSending(false);
    }
  }

  return (
    <aside
      className="pointer-events-auto flex max-h-[580px] w-full flex-col gap-4 overflow-y-auto panel border-l-2 border-l-primary p-5 sm:w-[410px]"
      role="dialog"
      aria-label={`${agent.name} 상세`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-primary">{agent.role}</p>
          <h3 className="mt-1 font-display text-[24px] font-semibold uppercase tracking-[-0.05em] text-ink">{agent.name}</h3>
        </div>
        <button onClick={onClose} className="btn btn-ghost !px-1.5" aria-label="닫기">
          <Icon name="x" size={16} />
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: m.hex, boxShadow: `0 0 10px ${m.hex}` }} />
        <span className="text-body-sm font-medium" style={{ color: m.hex }}>
          {m.ko}
        </span>
      </div>

      {model.hasJob ? (
        <dl className="space-y-0">
          <div className="kv"><dt>현재 작업</dt><dd className="truncate">{j.topic ?? "-"}</dd></div>
          <div className="kv"><dt>캠페인</dt><dd className="font-mono text-[12px]">{j.campaignId?.slice(0, 8) ?? "-"}</dd></div>
          <div className="kv"><dt>단계</dt><dd>{j.stage ?? "-"}</dd></div>
          <div className="kv"><dt>모드</dt><dd>{j.mode ?? "-"}</dd></div>
          <div className="kv"><dt>모델</dt><dd className="font-mono text-[12px]">{j.model ?? "-"}</dd></div>
          <div className="kv"><dt>Provider</dt><dd className="font-mono text-[12px]">{j.provider ?? "-"}</dd></div>
          <div className="kv"><dt>경과</dt><dd>{fmtElapsed(j.elapsedS)}</dd></div>
          <div className="kv"><dt>비용</dt><dd>{j.costUsd != null ? `$${j.costUsd.toFixed(4)}` : "-"}</dd></div>
        </dl>
      ) : (
        <p className="text-body-sm text-ink-subtle">
          {working ? "작업을 준비하고 있습니다." : "진행 중인 작업이 없습니다. 이 에이전트는 대기 중입니다."}
        </p>
      )}

      <div className="border-t border-hairline pt-3">
        <p className="mb-2 text-body-sm font-semibold text-ink">에이전트와 대화</p>
        <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg bg-white/55 p-2.5">
          {messages.map((message, index) => (
            <div key={index} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              <p className={`max-w-[88%] rounded-lg px-2.5 py-2 text-[13px] leading-relaxed ${message.role === "user" ? "bg-primary text-white" : "bg-white text-ink shadow-sm"}`}>
                {message.content}
              </p>
            </div>
          ))}
          {sending && <p className="text-[12px] text-ink-tertiary">답변을 작성하고 있습니다…</p>}
          <div ref={endRef} />
        </div>
        {chatError && <p className="mt-1.5 text-[12px] text-red-600">{chatError}</p>}
        <form onSubmit={sendMessage} className="mt-2 flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} className="input min-w-0 flex-1 !bg-white/80" placeholder="업무에 대해 질문하세요" maxLength={4000} />
          <button type="submit" className="btn btn-primary !px-3" disabled={sending || !draft.trim()} aria-label="메시지 보내기">
            <Icon name="send" size={15} />
          </button>
        </form>
      </div>

      <div className="mt-auto flex flex-wrap gap-2">
        {campaignHref ? (
          <Link href={campaignHref} className="btn btn-primary !py-1.5 !text-caption">
            <Icon name="arrow-right" size={14} />
            작업 보기
          </Link>
        ) : (
          <Link href="/create" className="btn btn-secondary !py-1.5 !text-caption">
            <Icon name="plus" size={14} />
            새 콘텐츠
          </Link>
        )}
        <Link href="/support" className="btn btn-secondary !py-1.5 !text-caption">
          로그 보기
        </Link>
        <Link href="/library" className="btn btn-ghost !py-1.5 !text-caption">
          관련 콘텐츠
        </Link>
      </div>
    </aside>
  );
}
