"use client";

/**
 * Gate for authenticated routes: while the session resolves, show a loader; on
 * 401 redirect to /login; otherwise render the app chrome. The backend remains
 * the real access authority — this only governs what the shell displays.
 */

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";
import { Nav } from "@/components/Nav";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { me, loading, error } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && (error === "unauthenticated" || !me)) {
      router.replace("/login");
    }
  }, [loading, error, me, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink/50">
        Loading session…
      </div>
    );
  }

  if (!me) return null; // redirecting

  return (
    <div className="flex min-h-screen">
      <aside className="w-64 shrink-0 border-r border-ink/10 bg-white">
        <Nav />
      </aside>
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}
