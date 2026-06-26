import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Presentation Notebook LLM",
  description: "Turn business documents into stakeholder-tailored presentations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
