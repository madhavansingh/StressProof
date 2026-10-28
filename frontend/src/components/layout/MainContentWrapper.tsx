"use client";

import { usePathname } from "next/navigation";
import { PortalSidebar } from "@/components/portal/PortalSidebar";
import { PortalTopNav } from "@/components/portal/PortalTopNav";

export function MainContentWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // On the landing page, render full bleed brutalist layout
  if (pathname === "/") {
    return <main className="w-full min-h-screen dot-grid-bg">{children}</main>;
  }

  // On dashboard and inner pages, render inside Brutalist Dark Shell
  return (
    <div className="flex min-h-screen w-full bg-background text-foreground dot-grid-bg">
      {/* Brutalist Left Sidebar */}
      <PortalSidebar />

      {/* Main Content Area with Brutalist TopNav */}
      <div className="flex-1 flex flex-col min-w-0">
        <PortalTopNav />
        <main className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
