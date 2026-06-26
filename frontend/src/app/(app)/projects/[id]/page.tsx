"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { GeneratePanel } from "@/components/project/GeneratePanel";
import { OutlinePanel } from "@/components/project/OutlinePanel";
import { SourcesPanel } from "@/components/project/SourcesPanel";
import { VersionHistoryPanel } from "@/components/project/VersionHistoryPanel";
import { api, type Project } from "@/services/api";

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const projectId = params.id;
  const [project, setProject] = useState<Project | null>(null);
  const [outlineId, setOutlineId] = useState<string | null>(null);
  const [historyKey, setHistoryKey] = useState(0);

  useEffect(() => {
    api.getProject(projectId).then(setProject).catch(() => setProject(null));
  }, [projectId]);

  return (
    <section className="flex flex-col gap-6">
      <header>
        <Link href="/projects" className="text-sm text-ink/50 hover:text-ink">
          ← Projects
        </Link>
        <h1 className="mt-1 text-2xl font-semibold text-ink">
          {project?.name ?? "Project"}
        </h1>
        <p className="mt-1 text-sm text-ink/60">
          Upload sources, build a validated outline, then generate an on-template deck.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="flex flex-col gap-6">
          <SourcesPanel projectId={projectId} />
          <GeneratePanel
            projectId={projectId}
            outlineId={outlineId}
            onSettled={() => setHistoryKey((k) => k + 1)}
          />
        </div>
        <OutlinePanel projectId={projectId} onOutlineReady={setOutlineId} />
      </div>

      <VersionHistoryPanel projectId={projectId} refreshKey={historyKey} />
    </section>
  );
}
