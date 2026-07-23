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
    <div className="flex min-h-[24rem] flex-1 flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <h2 className="text-lg font-semibold text-ink">{t("chat.title")}</h2>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
        {messages.length === 0 && !busy && (
          <p className="text-sm text-ink/40">{t("chat.empty")}</p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={m.role === "user" ? "self-end text-right" : "self-start"}
          >
            <div
              className={
                m.role === "user"
                  ? "inline-block max-w-[90%] rounded-2xl rounded-br-sm bg-accent px-4 py-2 text-sm text-white"
                  : "inline-block max-w-[90%] rounded-2xl rounded-bl-sm bg-ink/[0.04] px-4 py-2 text-sm text-ink/90"
              }
            >
              <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
            </div>
            {m.citations.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {m.citations.map((c, i) => (
                  <span
                    key={i}
                    title={c.snippet}
                    className="cursor-help rounded border border-ink/10 bg-ink/[0.03] px-1.5 py-0.5 text-[10px] text-ink/50"
                  >
                    {t("chat.cite")} {i + 1}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <p className="self-start text-sm text-ink/40">{t("chat.thinking")}</p>}
        <div ref={endRef} />
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <form onSubmit={onSubmit} className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("chat.placeholder")}
          className="flex-1 rounded-lg border border-ink/15 px-3 py-2 text-sm focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          {t("chat.send")}
        </button>
      </form>
    </div>
  );
}
