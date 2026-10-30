import type { Metadata, Viewport } from "next";
import { JetBrains_Mono } from "next/font/google";
import { MainContentWrapper } from "@/components/layout/MainContentWrapper";
import { Web3Providers } from "@/components/providers/Web3Providers";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Superconscious | StressProof — Brutalist Risk Settlement Layer",
  description:
    "An open, challengeable layer for AI-generated lending-market risk claims. Deterministic Python replayer, bonded optimistic attestations, and automated vault defense.",
};

export const viewport: Viewport = {
  themeColor: "#0f0f0f",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${jetbrainsMono.variable} dark`}>
      <body className="min-h-screen bg-background text-foreground font-mono antialiased selection:bg-[#ea580c] selection:text-white">
        <Web3Providers>
          <MainContentWrapper>{children}</MainContentWrapper>
        </Web3Providers>
      </body>
    </html>
  );
}
