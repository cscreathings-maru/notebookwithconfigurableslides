import type { ReactNode } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { AuthProvider } from "@/components/AuthProvider";

/** Authenticated layout: provides session context and the role-aware chrome. */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AuthGuard>{children}</AuthGuard>
    </AuthProvider>
  );
}
