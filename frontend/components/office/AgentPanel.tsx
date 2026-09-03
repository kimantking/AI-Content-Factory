"use client";

import Link from "next/link";
import { FormEvent, Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { AGENTS, STATE_META, type AgentId, type OfficeModel } from "./office-data";
import { Icon } from "@/components/ui/Icon";
import { chatWithAgent, type AgentChatMessage } from "@/lib/api";

const QUICK_QUESTIONS: Record<AgentId, string[]> = {
  research: ["지금 무엇을 조사해야 해?", "확인해야 할 출처를 정리해줘"],
  script: ["대본의 첫 문장을 추천해줘", "더 자연스러운 말투로 만드는 법은?"],
  video: ["영상 장면 구성을 추천해줘", "초반 이탈을 줄이는 방법은?"],
  publish: ["플랫폼별 제목을 추천해줘", "언제 게시하는 게 좋아?"],
};

function validChatMessages(value: unknown): AgentChatMessage[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is AgentChatMessage => {
    if (!row || typeof row !== "object") return false;
    const item = row as Record<string, unknown>;
    return (item.role === "user" || item.role === "assistant") && typeof item.content === "string";
  }).slice(-30);
}

const chatKey = (id: AgentId) => `acf-agent-chat-${id}`;
const pendingKey = (id: AgentId) => `acf-agent-pending-${id}`;

function readStoredMessages(id: AgentId): AgentChatMessage[] {
  try {
    return validChatMessages(JSON.parse(localStorage.getItem(chatKey(id)) || "[]"));
  } catch {
    return [];
  }
}

function notifyChatUpdate(id: AgentId) {
  window.dispatchEvent(new CustomEvent("acf-agent-chat-update", { detail: { id } }));
}

function fmtElapsed(s: number | null) {
  if (s == null) return "-";
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}분 ${Math.round(s % 60)}초` : `${Math.round(s)}초`;
}

function inlineMarkup(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g);
  return parts.map((part, index) => {
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
    if (link) {
      return <a key={index} href={link[2]} target="_blank" rel="noreferrer" className="font-medium text-primary underline decoration-primary/35 underline-offset-2 hover:decoration-primary">{link[1]}</a>;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index} className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[0.9em] text-ink">{part.slice(1, -1)}</code>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function StructuredAnswer({ content }: { content: string }) {
  return (
    <div className="space-y-2.5 break-words text-left text-[15px] leading-7 text-ink sm:text-[16px]">
      {content.split(/\r?\n/).map((raw, index) => {
        const line = raw.trim();
        if (!line) return <div key={index} className="h-1" aria-hidden="true" />;
        const heading = line.match(/^#{1,3}\s+(.+)$/) || line.match(/^\*\*(.+)\*\*$/);
        if (heading) return <h4 key={index} className="pt-1 text-[16px] font-bold leading-6 text-ink sm:text-[17px]">{inlineMarkup(heading[1])}</h4>;
        const bullet = line.match(/^[-*•]\s+(.+)$/);
        if (bullet) return <div key={index} className="grid grid-cols-[1rem_minmax(0,1fr)] gap-2"><span className="pt-[1px] font-bold text-primary">•</span><p>{inlineMarkup(bullet[1])}</p></div>;
        const ordered = line.match(/^(\d+)[.)]\s+(.+)$/);
        if (ordered) return <div key={index} className="grid grid-cols-[1.7rem_minmax(0,1fr)] gap-2"><span className="font-mono text-[13px] font-semibold text-primary">{ordered[1]}.</span><p>{inlineMarkup(ordered[2])}</p></div>;
        return <p key={index}>{inlineMarkup(line)}</p>;
      })}
    </div>
  );
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
  const [answerProgress, setAnswerProgress] = useState<number | null>(null);
  const [chatError, setChatError] = useState("");
  const [chatMeta, setChatMeta] = useState<{ provider: string; model: string; mock: boolean } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const progressResetRef = useRef<number | null>(null);

  useEffect(() => {
    const greeting: AgentChatMessage = { role: "assistant", content: `안녕하세요. ${agent.role}입니다. 무엇을 도와드릴까요?` };
    try {
      const saved = localStorage.getItem(chatKey(id));
      const parsed = saved ? JSON.parse(saved) : null;
      const restored = validChatMessages(parsed);
      setMessages(restored.length ? restored : [greeting]);
      const pending = Number(localStorage.getItem(pendingKey(id)) || 0);
      if (pending > 0) {
        setSending(true);
        setAnswerProgress(Math.min(92, 8 + Math.floor((Date.now() - pending) / 420) * 3));
      } else {
        setSending(false);
        setAnswerProgress(null);
      }
    } catch {
      setMessages([greeting]);
    }
    setDraft("");
    setChatError("");
    setChatMeta(null);
  }, [id, agent.role]);

  useEffect(() => {
    const refresh = (event: Event) => {
      const detail = (event as CustomEvent<{ id?: AgentId }>).detail;
      if (detail?.id !== id) return;
      const restored = readStoredMessages(id);
      if (restored.length) setMessages(restored);
      const pending = Number(localStorage.getItem(pendingKey(id)) || 0);
      setSending(pending > 0);
      setAnswerProgress(pending > 0 ? 92 : 100);
      if (!pending) progressResetRef.current = window.setTimeout(() => setAnswerProgress(null), 700);
    };
    window.addEventListener("acf-agent-chat-update", refresh);
    return () => window.removeEventListener("acf-agent-chat-update", refresh);
  }, [id]);

  useEffect(() => {
    const node = endRef.current;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [messages]);

  useEffect(() => {
    try {
      if (messages.length) localStorage.setItem(chatKey(id), JSON.stringify(messages.slice(-30)));
    } catch {
      // Private browsing/storage restrictions must never crash the office UI.
    }
  }, [id, messages]);

  useEffect(() => {
    if (!sending) return;
    const timer = window.setInterval(() => {
      setAnswerProgress((current) => {
        const value = current ?? 8;
        if (value >= 92) return 92;
        const step = value < 45 ? 7 : value < 75 ? 4 : 2;
        return Math.min(92, value + step);
      });
    }, 420);
    return () => window.clearInterval(timer);
  }, [sending]);

  useEffect(() => () => {
    if (progressResetRef.current !== null) window.clearTimeout(progressResetRef.current);
  }, []);

  async function sendText(text: string) {
    text = text.trim();
    if (!text || sending) return;
    const next = [...messages, { role: "user", content: text } as AgentChatMessage];
    setMessages(next);
    setDraft("");
    setSending(true);
    if (progressResetRef.current !== null) window.clearTimeout(progressResetRef.current);
    setAnswerProgress(8);
    try {
      localStorage.setItem(chatKey(id), JSON.stringify(next.slice(-30)));
      localStorage.setItem(pendingKey(id), String(Date.now()));
    } catch {
      // The request can still run in memory when storage is unavailable.
    }
    setChatError("");
    try {
      const result = await chatWithAgent(id, text, next.slice(0, -1), {
        topic: j.topic,
        stage: j.stage,
        mode: j.mode,
        campaign_id: j.campaignId,
      });
      const reply: AgentChatMessage = { role: "assistant", content: result.reply };
      const latest = readStoredMessages(id);
      const completed = [...(latest.length ? latest : next), reply].slice(-30);
      try {
        localStorage.setItem(chatKey(id), JSON.stringify(completed));
        localStorage.removeItem(pendingKey(id));
      } catch {
        // Keep the in-memory result when browser storage is unavailable.
      }
      setMessages(completed);
      setChatMeta({ provider: result.provider, model: result.model, mock: result.mock });
      setAnswerProgress(100);
      notifyChatUpdate(id);
    } catch {
      setChatError("AI와 연결하지 못했습니다. 백엔드와 AI 설정을 확인해 주세요.");
      try {
        localStorage.removeItem(pendingKey(id));
      } catch {
        // Ignore storage restrictions.
      }
      notifyChatUpdate(id);
    } finally {
      setSending(false);
      progressResetRef.current = window.setTimeout(() => setAnswerProgress(null), 700);
    }
  }

  async function sendMessage(e: FormEvent) {
    e.preventDefault();
    await sendText(draft);
  }

  function clearChat() {
    const greeting: AgentChatMessage = { role: "assistant", content: `새 대화를 시작합니다. ${agent.role}에게 무엇이든 물어보세요.` };
    setMessages([greeting]);
    setChatMeta(null);
    setAnswerProgress(null);
    try {
      localStorage.removeItem(chatKey(id));
      localStorage.removeItem(pendingKey(id));
    } catch {
      // The in-memory conversation is still reset when browser storage is unavailable.
    }
  }

  return (
    <aside
      className="pointer-events-auto relative isolate flex h-[100dvh] max-h-none w-full flex-col gap-3 overflow-hidden border-l-2 border-l-primary bg-[#fffafd]/98 p-4 shadow-[0_24px_70px_rgba(47,22,37,.32)] backdrop-blur-xl sm:h-[min(760px,calc(100vh-2rem))] sm:w-[min(720px,calc(100vw-3rem))] sm:rounded-2xl sm:p-6"
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

      <div className="flex min-h-0 flex-1 flex-col border-t border-hairline pt-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-body-sm font-semibold text-ink">에이전트와 대화</p>
          <button type="button" onClick={clearChat} className="text-[12px] text-ink-tertiary hover:text-primary">대화 초기화</button>
        </div>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {QUICK_QUESTIONS[id].map((question) => (
            <button key={question} type="button" onClick={() => sendText(question)} disabled={sending} className="rounded-md border border-primary/25 bg-primary/5 px-2 py-1 text-left text-[12px] text-ink-subtle hover:bg-primary/10 disabled:opacity-50">
              {question}
            </button>
          ))}
        </div>
        <div className="min-h-[220px] flex-1 space-y-3 overflow-y-auto overscroll-contain rounded-xl border border-primary/10 bg-white/65 p-3 sm:min-h-[300px] sm:p-4">
          {messages.map((message, index) => (
            <div key={index} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`rounded-xl px-3.5 py-3 sm:px-4 ${message.role === "user" ? "max-w-[88%] bg-primary text-[15px] leading-6 text-white" : "w-full bg-white shadow-sm ring-1 ring-black/[0.04]"}`}>
                {message.role === "assistant" ? <StructuredAnswer content={message.content} /> : <p className="whitespace-pre-wrap break-words text-left">{message.content}</p>}
              </div>
            </div>
          ))}
          {sending && <p className="text-[12px] text-ink-tertiary">답변을 작성하고 있습니다…</p>}
          <div ref={endRef} />
        </div>
        {answerProgress !== null && (
          <div className="mt-2" role="status" aria-live="polite" aria-label={`응답 준비 ${answerProgress}%`}>
            <div className="mb-1 flex items-center justify-between text-[12px] text-ink-subtle">
              <span>{answerProgress === 100 ? "답변 완료" : "응답 준비 중"}</span>
              <span className="font-mono font-semibold text-primary">{answerProgress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-primary/10">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#ef9fc6] via-[#d77bab] to-primary transition-[width] duration-300 ease-out"
                style={{ width: `${answerProgress}%` }}
              />
            </div>
          </div>
        )}
        {chatError && <p className="mt-1.5 text-[12px] text-red-600">{chatError}</p>}
        {chatMeta && (
          <p className="mt-1.5 text-[11px] text-ink-tertiary">
            {chatMeta.mock ? "모의 AI" : chatMeta.provider || "AI"} · {chatMeta.model || "모델 확인 중"}
          </p>
        )}
        <form onSubmit={sendMessage} className="mt-3 flex items-end gap-2">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} className="input min-h-[48px] min-w-0 flex-1 resize-none !bg-white/90 py-3 text-[16px] leading-6" placeholder="업무에 대해 질문하세요" maxLength={4000} rows={2} />
          <button type="submit" className="btn btn-primary h-12 !px-4" disabled={sending || !draft.trim()} aria-label="메시지 보내기">
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
