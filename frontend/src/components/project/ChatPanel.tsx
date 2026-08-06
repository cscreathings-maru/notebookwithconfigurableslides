"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChatSessionBar } from "@/components/project/ChatSessionBar";
import { OutlineBuilderCard } from "@/components/project/OutlineBuilderCard";
import { Markdown } from "@/components/ui/Markdown";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type ChatMessage, type ChatSession } from "@/services/api";

/** First page size. Older turns load on demand rather than on every mount. */
const PAGE_SIZE = 50;
/** How long an undo stays offered after deleting a thread. */
const UNDO_WINDOW_MS = 8000;
/** Typing this opens the generation card (Phase D). Never inferred from prose. */
const GENERATE_COMMAND = "/generate";
/** F4: longer than this collapses inline with "Lihat selengkapnya", opening the
 *  full-height reader instead of growing the bubble indefinitely. */
const READER_COLLAPSE_CHARS = 1200;

/** Which citation snippet is expanded; at most one across the whole thread. */
interface ActiveCitation {
  messageId: string;
  index: number;
}

function isCitationOpen(
  active: ActiveCitation | null,
  messageId: string,
  index: number,
): boolean {
  return active?.messageId === messageId && active.index === index;
}

/**
 * Chat with sources — RAG Q&A with citations. A `pendingQuestion` (e.g. a clicked
 * suggested question from the guide) is sent automatically, then cleared.
 */
export function ChatPanel({
  projectId,
  pendingQuestion,
  onConsumed,
  onOpenReader,
  onReaderMessageUpdated,
}: {
  projectId: string;
  pendingQuestion: string | null;
  onConsumed: () => void;
  /** F4: open a message in the right-rail reader tab. */
  onOpenReader?: (message: ChatMessage) => void;
  /** F1: tell the reader (if this message happens to be open there) that it grew. */
  onReaderMessageUpdated?: (message: ChatMessage) => void;
}) {
  const t = useT();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [hasOlder, setHasOlder] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<ActiveCitation | null>(null);
  const [generateFor, setGenerateFor] = useState<{ messageId?: string } | null>(null);
  const [undo, setUndo] = useState<{ session: ChatSession } | null>(null);
  const [continuingId, setContinuingId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const list = await api.listChatSessions(projectId);
      setSessions(list);
      // Follow the server's ordering (most recently used first) rather than inventing
      // a selection; only fall back when the active thread has gone away.
      setActiveSessionId((current) =>
        current && list.some((s) => s.id === current) ? current : (list[0]?.id ?? null),
      );
    } catch {
      /* ignore transient */
    }
  }, [projectId]);

  const load = useCallback(
    async (sessionId?: string | null) => {
      try {
        const page = await api.listChat(projectId, {
          sessionId: sessionId ?? undefined,
          limit: PAGE_SIZE,
        });
        setMessages(page);
        setHasOlder(page.length >= PAGE_SIZE);
      } catch {
        /* ignore transient */
      }
    },
    [projectId],
  );

  const loadOlder = useCallback(async () => {
    const oldest = messages[0];
    if (!oldest) return;
    try {
      const older = await api.listChat(projectId, {
        sessionId: activeSessionId ?? undefined,
        limit: PAGE_SIZE,
        before: oldest.created_at,
      });
      setHasOlder(older.length >= PAGE_SIZE);
      setMessages((prev) => [...older, ...prev]);
    } catch {
      /* ignore transient */
    }
  }, [projectId, activeSessionId, messages]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Reload the thread whenever the active session changes. `undefined` on first paint
  // (before sessions arrive) targets the project's most recent session server-side,
  // so a project that has never been chatted with still renders.
  useEffect(() => {
    load(activeSessionId);
  }, [load, activeSessionId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  // Escape closes an expanded citation, the convention for any dismissible disclosure.
  useEffect(() => {
    if (!activeCitation) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActiveCitation(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeCitation]);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      setBusy(true);
      setError(null);
      // Optimistic user bubble; the server persists both turns.
      setMessages((prev) => [
        ...prev,
        {
          id: `pending-${Date.now()}`,
          role: "user",
          content: q,
          citations: [],
          created_at: new Date().toISOString(),
          truncated: false,
        },
      ]);
      try {
        await api.sendChat(projectId, q, activeSessionId ?? undefined);
        await load(activeSessionId);
        // The first question names the thread, so the switcher label is now stale.
        await loadSessions();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : t("chat.failed"));
      } finally {
        setBusy(false);
      }
    },
    [busy, projectId, load, loadSessions, activeSessionId, t],
  );

  // Auto-send a question routed in from the guide's suggested chips.
  useEffect(() => {
    if (pendingQuestion) {
      send(pendingQuestion);
      onConsumed();
    }
  }, [pendingQuestion, send, onConsumed]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const raw = input.trim();
    // Phase D: an EXPLICIT command opens the generation card. Nothing about a message
    // is ever classified as generate-intent -- generation is billable and irreversible,
    // so it takes a deliberate action, then a deliberate confirmation.
    if (raw.toLowerCase() === GENERATE_COMMAND) {
      setInput("");
      setGenerateFor({});
      return;
    }
    setInput("");
    send(raw);
  };

  // --- session actions --------------------------------------------------------

  const createSession = async () => {
    try {
      const created = await api.createChatSession(projectId);
      setSessions((prev) => [created, ...prev]);
      setActiveSessionId(created.id);
      setMessages([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("chat.failed"));
    }
  };

  const renameSession = async (sessionId: string, title: string) => {
    // Optimistic: renaming is cheap and reversible, so the label should not lag.
    setSessions((prev) => prev.map((s) => (s.id === sessionId ? { ...s, title } : s)));
    try {
      await api.renameChatSession(sessionId, title);
    } catch {
      await loadSessions();
    }
  };

  const deleteSession = async (sessionId: string) => {
    const victim = sessions.find((s) => s.id === sessionId);
    if (!victim) return;
    const remaining = sessions.filter((s) => s.id !== sessionId);
    setSessions(remaining);
    if (activeSessionId === sessionId) setActiveSessionId(remaining[0]?.id ?? null);
    try {
      // Server-side this is an archive, so `undo` restores the messages too.
      await api.deleteChatSession(sessionId);
      setUndo({ session: victim });
    } catch (err) {
      await loadSessions();
      setError(err instanceof ApiError ? err.message : t("chat.failed"));
    }
  };

  const undoDelete = async () => {
    if (!undo) return;
    const { session } = undo;
    setUndo(null);
    try {
      await api.restoreChatSession(session.id);
      await loadSessions();
      setActiveSessionId(session.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("chat.failed"));
    }
  };

  // The undo offer expires on its own; a toast that never leaves is its own bug.
  useEffect(() => {
    if (!undo) return;
    const timer = setTimeout(() => setUndo(null), UNDO_WINDOW_MS);
    return () => clearTimeout(timer);
  }, [undo]);

  // F1: append the rest of a truncated answer, in place -- same message id, grown
  // content, flag cleared. Also pokes the reader tab in case this message is open
  // there, so it does not keep showing a stale, still-truncated copy.
  const continueMessage = useCallback(
    async (messageId: string) => {
      setContinuingId(messageId);
      setError(null);
      try {
        const updated = await api.continueChat(messageId);
        setMessages((prev) => prev.map((m) => (m.id === messageId ? updated : m)));
        onReaderMessageUpdated?.(updated);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : t("chat.failed"));
      } finally {
        setContinuingId(null);
      }
    },
    [t, onReaderMessageUpdated],
  );

  return (
    <div className="card flex flex-col h-full min-h-0 relative">
      <div className="p-4 border-b border-gray-100 flex items-center gap-2 bg-white rounded-t-xl z-10 shadow-sm shrink-0">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-accent">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <h2 className="text-base font-semibold text-gray-900">{t("chat.title")}</h2>
      </div>

      <div className="shrink-0 border-b border-gray-100 bg-white px-4 py-2">
        <ChatSessionBar
          sessions={sessions}
          activeId={activeSessionId}
          busy={busy}
          onSelect={setActiveSessionId}
          onCreate={createSession}
          onRename={renameSession}
          onDelete={deleteSession}
        />
      </div>

      {undo && (
        <div
          role="status"
          className="flex shrink-0 items-center gap-3 border-b border-gray-100 bg-gray-900 px-4 py-2 text-xs text-white"
        >
          <span className="truncate">{t("chat.session.deleted")}</span>
          <button
            type="button"
            onClick={undoDelete}
            className="ml-auto shrink-0 font-semibold text-accent-light underline underline-offset-2 hover:text-white"
          >
            {t("chat.session.undo")}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5 bg-gray-50/50">
        {hasOlder && (
          <button
            type="button"
            onClick={loadOlder}
            className="mx-auto shrink-0 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-600 hover:border-accent hover:text-accent"
          >
            {t("chat.loadOlder")}
          </button>
        )}

        {messages.length === 0 && !busy && (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-12 h-12 bg-white shadow-sm rounded-full flex items-center justify-center mb-3">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6 text-gray-400">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
              </svg>
            </div>
            <p className="text-sm text-gray-500 max-w-xs">{t("chat.empty")}</p>
          </div>
        )}
        
        {messages.map((m) => {
          const isLong = m.content.length > READER_COLLAPSE_CHARS;
          const preview = isLong
            ? `${m.content.slice(0, READER_COLLAPSE_CHARS)}…`
            : m.content;
          return (
          <div
            key={m.id}
            className={`flex flex-col animate-slide-up ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`relative px-4 py-3 text-[15px] leading-relaxed max-w-[90%] md:max-w-[85%] shadow-sm ${
                m.role === "user"
                  ? "bg-accent text-white rounded-2xl rounded-tr-sm"
                  : "bg-white border border-gray-100 text-gray-800 rounded-2xl rounded-tl-sm"
              }`}
            >
              <Markdown density="compact">{preview}</Markdown>
              {/* F4: the reader panel, not the bubble, is where a long answer is meant
                  to be read in full -- an unbounded bubble is the scroll problem
                  Phase A fixed, reintroduced one message at a time. */}
              {isLong && (
                <button
                  type="button"
                  onClick={() => onOpenReader?.(m)}
                  className={`mt-2 text-xs font-semibold underline underline-offset-2 ${
                    m.role === "user" ? "text-white/90 hover:text-white" : "text-accent"
                  }`}
                >
                  {t("reader.seeMore")}
                </button>
              )}
            </div>
            {/* F1: the provider's own signal, surfaced. A cut-off answer used to
                render identically to a complete one -- this is the visible marker
                plus the one action that fixes it, right where the cut happened. */}
            {m.truncated && (
              <div className="mt-1.5 flex w-full max-w-[90%] items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-800 md:max-w-[85%]">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5 shrink-0">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span className="flex-1">{t("chat.truncated")}</span>
                <button
                  type="button"
                  onClick={() => continueMessage(m.id)}
                  disabled={continuingId === m.id}
                  className="shrink-0 font-semibold underline underline-offset-2 hover:no-underline disabled:opacity-50"
                >
                  {continuingId === m.id ? t("chat.continuing") : t("chat.continue")}
                </button>
              </div>
            )}
            {m.citations.length > 0 && (
              <div className="mt-2 flex w-full max-w-[90%] flex-col gap-2 md:max-w-[85%]">
                <div className="flex flex-wrap gap-1.5">
                  {m.citations.map((c, i) => {
                    const active = isCitationOpen(activeCitation, m.id, i);
                    return (
                      <button
                        key={i}
                        type="button"
                        aria-expanded={active}
                        aria-controls={`cite-${m.id}-${i}`}
                        onClick={() =>
                          setActiveCitation(active ? null : { messageId: m.id, index: i })
                        }
                        className={`rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent-light ${
                          active
                            ? "border-accent bg-accent text-white"
                            : "border-accent/20 bg-accent/5 text-accent hover:bg-accent/10"
                        }`}
                      >
                        {t("chat.cite")} {i + 1}
                      </button>
                    );
                  })}
                </div>
                {/* Inline disclosure, NOT a floating popover: the message list is an
                    `overflow-y-auto` container, which clips absolutely-positioned
                    children regardless of z-index. A popover above the first visible
                    message was cut off. Expanding in flow also reads better on mobile
                    and needs no blur timer to dismiss. */}
                {m.citations.map((c, i) =>
                  isCitationOpen(activeCitation, m.id, i) ? (
                    <div
                      key={`panel-${i}`}
                      id={`cite-${m.id}-${i}`}
                      role="region"
                      aria-label={`${t("chat.cite")} ${i + 1}`}
                      className="animate-fade-in rounded-lg border border-accent/20 bg-accent/5 p-3 text-xs leading-relaxed text-gray-700"
                    >
                      {c.snippet}
                    </div>
                  ) : null,
                )}
              </div>
            )}
            {/* Offered, never auto-run. The card that opens shows every parameter
                before anything billable happens. */}
            {m.role === "assistant" && !m.id.startsWith("pending-") && (
              <button
                type="button"
                onClick={() => setGenerateFor({ messageId: m.id })}
                className="mt-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium text-gray-400 transition-colors hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent-light"
              >
                {t("generate.fromThis")}
              </button>
            )}
          </div>
          );
        })}

        {busy && (
          <div className="self-start animate-fade-in">
            <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm flex gap-1.5 items-center h-[46px]">
              <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
              <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
              <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            </div>
          </div>
        )}
        <div ref={endRef} className="h-px w-full" />
      </div>

      <div className="p-4 bg-white rounded-b-xl border-t border-gray-100 shrink-0">
        {error && (
          <div role="alert" className="mb-3 rounded-lg bg-red-50 p-2.5 text-sm text-red-600">
            {error}
          </div>
        )}

        {generateFor && (
          <div className="mb-3">
            <OutlineBuilderCard
              projectId={projectId}
              chatMessageId={generateFor.messageId}
              onCancel={() => setGenerateFor(null)}
              onGenerated={() => setGenerateFor(null)}
            />
          </div>
        )}

        <form onSubmit={onSubmit} className="relative flex items-center gap-2">
          <button
            type="button"
            onClick={() => setGenerateFor({})}
            aria-label={t("generate.open")}
            title={`${t("generate.open")} (${GENERATE_COMMAND})`}
            className="shrink-0 rounded-full border border-gray-200 bg-white p-2 text-gray-500 transition-colors hover:border-accent hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent-light"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("chat.placeholder")}
            className="w-full rounded-full border border-gray-200 bg-gray-50 pl-4 pr-12 py-3 text-sm focus:bg-white focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-light transition-all shadow-sm"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="absolute right-1.5 w-8 h-8 flex items-center justify-center rounded-full bg-accent text-white disabled:opacity-40 hover:bg-accent-hover transition-colors shadow-sm disabled:shadow-none"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 ml-0.5">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
