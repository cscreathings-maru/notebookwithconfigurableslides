"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/project/ChatPanel";
import { GuidePanel } from "@/components/project/GuidePanel";
import { SourcesPanel } from "@/components/project/SourcesPanel";
import { StudioPanel } from "@/components/project/StudioPanel";
import { api, type Project } from "@/services/api";

/**
 * NotebookLM-style 3-pane workspace:
 *   Sources (left) · Guide + Chat (center) · Studio (right).
 */
export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const projectId = params.id;
  const [project, setProject] = useState<Project | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  useEffect(() => {
    api.getProject(projectId).then(setProject).catch(() => setProject(null));
  }, [projectId]);

  return (
    <section className="flex flex-col gap-6">
      <header>
        <Link href="/projects" className="text-sm text-ink/50 hover:text-ink">
          ← Projects
        </Link>
        <h1 className="mt-1 text-2xl font-semibold text-ink">{project?.name ?? "Notebook"}</h1>
        <p className="mt-1 text-sm text-ink/60">
          Upload sources, explore them with an auto guide and chat, then generate configurable
          slides.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Sources rail */}
        <div className="lg:col-span-3">
          <SourcesPanel projectId={projectId} />
        </div>

        {/* Guide + chat */}
        <div className="flex flex-col gap-6 lg:col-span-5">
          <GuidePanel projectId={projectId} onAsk={setPendingQuestion} />
          <ChatPanel
            projectId={projectId}
            pendingQuestion={pendingQuestion}
            onConsumed={() => setPendingQuestion(null)}
          />
        </div>

        {/* Studio */}
        <div className="lg:col-span-4">
          <StudioPanel projectId={projectId} />
        </div>
      </div>
    </section>
  );
}
