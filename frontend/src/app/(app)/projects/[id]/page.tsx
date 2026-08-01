"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/project/ChatPanel";
import { GuidePanel } from "@/components/project/GuidePanel";
import { SourcesPanel } from "@/components/project/SourcesPanel";
import { StudioPanel } from "@/components/project/StudioPanel";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, type Project } from "@/services/api";

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const projectId = params.id;
  const t = useT();
  const [project, setProject] = useState<Project | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  const [mobileTab, setMobileTab] = useState<"sources" | "chat" | "right">("chat");
  const [rightTab, setRightTab] = useState<"guide" | "studio">("guide");
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    api.getProject(projectId).then(setProject).catch(() => setProject(null));
  }, [projectId]);

  const rightRail = (
    <div className="flex flex-col min-h-0 h-full bg-white card rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <div className="flex border-b border-gray-100 shrink-0 bg-gray-50/50">
        <button 
          onClick={() => setRightTab("guide")}
          className={`flex-1 py-3.5 text-sm font-medium border-b-2 transition-colors ${rightTab === 'guide' ? 'border-accent text-accent bg-white' : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'}`}
        >
          {t("rightRail.guide")}
        </button>
        <button 
          onClick={() => setRightTab("studio")}
          className={`flex-1 py-3.5 text-sm font-medium border-b-2 transition-colors ${rightTab === 'studio' ? 'border-accent text-accent bg-white' : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'}`}
        >
          {t("rightRail.studio")}
        </button>
        <button
          type="button"
          onClick={() => setDrawerOpen(false)}
          aria-label={t("rightRail.close")}
          className="hidden lg:flex xl:hidden p-3.5 items-center justify-center text-gray-400 hover:text-gray-600 border-l border-gray-100"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {rightTab === "guide" ? (
          <GuidePanel projectId={projectId} onAsk={(q) => {
            setPendingQuestion(q);
            setMobileTab("chat");
            setDrawerOpen(false);
          }} />
        ) : (
          <StudioPanel projectId={projectId} />
        )}
      </div>
    </div>
  );

  return (
    // No bottom padding: AuthGuard's scroll container already applies `pb-16`, and in a
    // fixed-height workspace every reclaimed pixel goes to the message list.
    <section className="flex-1 flex flex-col gap-4 lg:gap-6 animate-fade-in min-h-0">
      <header className="flex flex-col gap-2 shrink-0">
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
        <div className="flex items-center justify-between">
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
              {project && <p className="text-sm text-gray-500 hidden sm:block">{t("workspace.subtitle")}</p>}
            </div>
          </div>
          <button 
            onClick={() => setDrawerOpen(true)}
            className="hidden lg:flex xl:hidden btn-secondary items-center gap-2"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line></svg>
            {t("workspace.openTools")}
          </button>
        </div>
      </header>

      <div className="flex-1 flex flex-col min-h-0 relative">
        <div className="grid grid-cols-1 lg:grid-cols-8 xl:grid-cols-12 gap-6 min-h-0 flex-1 relative overflow-hidden xl:overflow-visible">
          
          {/* Sources rail */}
          <div className={`flex-col min-h-0 lg:col-span-3 ${mobileTab === 'sources' ? 'flex' : 'hidden lg:flex'}`}>
            <SourcesPanel projectId={projectId} />
          </div>

          {/* Chat rail */}
          <div className={`flex-col min-h-0 lg:col-span-5 ${mobileTab === 'chat' ? 'flex' : 'hidden lg:flex'}`}>
            <ChatPanel
              projectId={projectId}
              pendingQuestion={pendingQuestion}
              onConsumed={() => setPendingQuestion(null)}
            />
          </div>

          {/* Right rail (Guide + Studio Tabs) */}
          <div className={`flex-col min-h-0 xl:col-span-4
            ${mobileTab === 'right' ? 'flex' : 'hidden lg:flex'}
            lg:absolute lg:top-0 lg:right-0 lg:bottom-0 lg:w-96 lg:shadow-2xl lg:z-50 xl:static xl:w-auto xl:shadow-none xl:z-auto
            transition-transform duration-300 ease-in-out
            ${!drawerOpen
              ? // `invisible` (not just translated off-screen) so the closed drawer's
                // controls leave the tab order — otherwise keyboard users tab into an
                // off-canvas panel they cannot see. Restored at xl, where it is docked.
                'lg:invisible lg:translate-x-full xl:visible xl:translate-x-0'
              : 'lg:translate-x-0'}
          `}>
            {rightRail}
          </div>

          {/* Drawer overlay */}
          {drawerOpen && (
            <div 
              className="hidden lg:block xl:hidden absolute inset-0 bg-gray-900/20 z-40 rounded-xl"
              onClick={() => setDrawerOpen(false)}
            />
          )}
        </div>

        {/* Mobile bottom tab bar */}
        <div className="lg:hidden flex border-t border-gray-200 bg-white p-2 mt-4 shrink-0 justify-around rounded-2xl shadow-sm">
          <button 
            onClick={() => setMobileTab("sources")}
            className={`flex flex-col items-center gap-1 p-2 rounded-xl flex-1 transition-colors ${mobileTab === 'sources' ? 'text-accent bg-accent/10' : 'text-gray-500 hover:bg-gray-50'}`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span className="text-[11px] font-medium uppercase tracking-wider">{t("tab.sources")}</span>
          </button>
          <button 
            onClick={() => setMobileTab("chat")}
            className={`flex flex-col items-center gap-1 p-2 rounded-xl flex-1 transition-colors ${mobileTab === 'chat' ? 'text-accent bg-accent/10' : 'text-gray-500 hover:bg-gray-50'}`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="text-[11px] font-medium uppercase tracking-wider">{t("tab.chat")}</span>
          </button>
          <button 
            onClick={() => setMobileTab("right")}
            className={`flex flex-col items-center gap-1 p-2 rounded-xl flex-1 transition-colors ${mobileTab === 'right' ? 'text-accent bg-accent/10' : 'text-gray-500 hover:bg-gray-50'}`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
            <span className="text-[11px] font-medium uppercase tracking-wider">{t("tab.tools")}</span>
          </button>
        </div>
      </div>
    </section>
  );
}
