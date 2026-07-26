"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/project/ChatPanel";
import { GuidePanel } from "@/components/project/GuidePanel";
import { SourcesPanel } from "@/components/project/SourcesPanel";
import { StudioPanel } from "@/components/project/StudioPanel";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, type Project } from "@/services/api";

/**
 * NotebookLM-style 3-pane workspace:
 *   Sources (left) · Guide + Chat (center) · Studio (right).
 */
export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const projectId = params.id;
  const t = useT();
  const [project, setProject] = useState<Project | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  useEffect(() => {
    api.getProject(projectId).then(setProject).catch(() => setProject(null));
  }, [projectId]);

  return (
    <section className="flex flex-col gap-6 animate-fade-in h-full pb-8">
      <header className="flex flex-col gap-2">
        <nav aria-label="Breadcrumb">
          <Link 
            href="/projects" 
            className="inline-flex items-center gap-1 text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            {t("workspace.back")}
          </Link>
        </nav>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-faint text-accent shadow-sm">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              {project?.name ?? (
                <span className="inline-block w-48 h-8 animate-pulse bg-gray-200 rounded-md"></span>
              )}
            </h1>
            {project && <p className="text-sm text-gray-500">{t("workspace.subtitle")}</p>}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 min-h-0 flex-1">
        {/* Sources rail */}
        <div className="lg:col-span-3 flex flex-col min-h-[400px]">
          <SourcesPanel projectId={projectId} />
        </div>

        {/* Guide + chat */}
        <div className="flex flex-col gap-6 lg:col-span-5 min-h-[500px]">
          <GuidePanel projectId={projectId} onAsk={setPendingQuestion} />
          <ChatPanel
            projectId={projectId}
            pendingQuestion={pendingQuestion}
            onConsumed={() => setPendingQuestion(null)}
          />
        </div>

        {/* Studio */}
        <div className="lg:col-span-4 flex flex-col min-h-[500px]">
          <StudioPanel projectId={projectId} />
        </div>
      </div>
    </section>
  );
}
