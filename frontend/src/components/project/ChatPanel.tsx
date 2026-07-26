"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type ChatMessage } from "@/services/api";

/**
 * Chat with sources — RAG Q&A with citations. A `pendingQuestion` (e.g. a clicked
 * suggested question from the guide) is sent automatically, then cleared.
 */
export function ChatPanel({
  projectId,
  pendingQuestion,
  onConsumed,
}: {
  projectId: string;
  pendingQuestion: string | null;
  onConsumed: () => void;
}) {
  const t = useT();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      setMessages(await api.listChat(projectId));
    } catch {
      /* ignore transient */
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

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
        },
      ]);
      try {
        await api.sendChat(projectId, q);
        await load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : t("chat.failed"));
      } finally {
        setBusy(false);
      }
    },
    [busy, projectId, load, t],
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
    const q = input;
    setInput("");
    send(q);
  };

  return (
    <div className="card flex flex-col h-full min-h-[400px]">
      <div className="p-4 border-b border-gray-100 flex items-center gap-2 bg-white rounded-t-xl z-10 shadow-sm">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-accent">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <h2 className="text-base font-semibold text-gray-900">{t("chat.title")}</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5 bg-gray-50/50">
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
        
        {messages.map((m) => (
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
              <p className="whitespace-pre-wrap">{m.content}</p>
            </div>
            {m.citations.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5 justify-start">
                {m.citations.map((c, i) => (
                  <span
                    key={i}
                    title={c.snippet}
                    className="cursor-help rounded-md border border-accent/20 bg-accent/5 px-2 py-0.5 text-[11px] font-medium text-accent hover:bg-accent/10 transition-colors"
                  >
                    {t("chat.cite")} {i + 1}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        
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

      <div className="p-4 bg-white rounded-b-xl border-t border-gray-100">
        {error && (
          <div role="alert" className="mb-3 rounded-lg bg-red-50 p-2.5 text-sm text-red-600">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="relative flex items-center">
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
