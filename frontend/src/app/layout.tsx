import type { Metadata } from "next";
import { Navbar } from "@/components/layout/Navbar";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "StressProof",
  description: "An open, challengeable layer for AI-generated lending-market risk claims.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-50 font-sans text-zinc-900 antialiased dark:bg-zinc-900 dark:text-zinc-50">
        <Navbar />
        <main className="container mx-auto p-4 md:p-6">{children}</main>
      </body>
    </html>
  );
}
