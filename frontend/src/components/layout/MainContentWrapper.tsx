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

  // On dashboard and inner pages, render inside Brutalist Dark Shell with fixed sidebar
  return (
    <div className="flex h-screen w-full bg-background text-foreground dot-grid-bg overflow-hidden">
      {/* Brutalist Left Sidebar (Fixed / Pinned) */}
      <PortalSidebar />

      {/* Main Content Area with Fixed TopNav and Independent Scroll */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <PortalTopNav />
        <main className="flex-1 p-3.5 sm:p-6 md:p-8 overflow-y-auto max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
