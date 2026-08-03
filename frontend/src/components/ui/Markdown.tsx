"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders AI-authored text as markdown.
 *
 * Every model this app talks to answers in markdown, and the UI used to print it
 * verbatim — `<p>{content}</p>` — so chat replies and notebook summaries showed raw
 * `**bold**` and `-` bullets. That reads as a model defect but is purely a rendering
 * one; no model change fixes it.
 *
 * **Raw HTML is deliberately not enabled.** `react-markdown` ignores embedded HTML
 * unless `rehype-raw` is added, so model output cannot inject markup. Do not add that
 * plugin here: this component renders text the model wrote, which is untrusted input
 * derived in turn from user-uploaded documents.
 *
 * One component for every AI-authored surface, so chat, the guide and anything later
 * cannot drift apart in how they look.
 */
interface MarkdownProps {
  children: string;
  /** `compact` suits chat bubbles; `default` suits longer reading surfaces. */
  density?: "default" | "compact";
}

export function Markdown({ children, density = "default" }: MarkdownProps) {
  const gap = density === "compact" ? "space-y-2" : "space-y-3";
  return (
    <div className={`${gap} text-[15px] leading-relaxed break-words`}>
      <ReactMarkdown
        // GFM only: tables, strikethrough, task lists, autolinks. Models emit these
        // routinely in summaries. It adds no HTML passthrough.
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="whitespace-pre-wrap">{children}</p>,
          strong: ({ children }) => (
            <strong className="font-semibold text-current">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => (
            <ul className="list-disc space-y-1 pl-5 marker:text-current/50">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal space-y-1 pl-5 marker:text-current/50">{children}</ol>
          ),
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          h1: ({ children }) => <h3 className="text-base font-semibold">{children}</h3>,
          h2: ({ children }) => <h4 className="text-[15px] font-semibold">{children}</h4>,
          h3: ({ children }) => <h5 className="text-sm font-semibold">{children}</h5>,
          code: ({ children }) => (
            <code className="rounded bg-black/5 px-1 py-0.5 font-mono text-[13px]">
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-lg bg-black/5 p-3 font-mono text-[13px]">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-current/20 pl-3 italic opacity-90">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            // Model-authored links go to third parties: never leak the referrer and
            // never hand the opened page a live `window.opener`.
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="underline underline-offset-2 hover:opacity-80"
            >
              {children}
            </a>
          ),
          // Wide tables must scroll inside their own box, never widen the column.
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-current/15 px-2 py-1 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-current/15 px-2 py-1">{children}</td>
          ),
          hr: () => <hr className="border-current/15" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
