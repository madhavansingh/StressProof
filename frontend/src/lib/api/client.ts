/**
 * Backend API client for StressProof.
 *
 * Direct reads (GET) connect straight to the public backend URL.
 * Authenticated writes (POST) route through the Next.js API server proxy
 * (/api/stress/run) to prevent leaking the backend write token to browser bundles.
 */

import { FeedResponse } from "@/types";

export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

export async function fetchDatasets() {
  const res = await fetch(`${BACKEND_URL}/datasets`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to load datasets");
  return res.json();
}

export async function runStressTest(datasetId: string, shockBps: number, rationale?: string) {
  // Routes to the Next.js server route handler (/api/stress/run)
  // which securely appends the private API_WRITE_TOKEN server-side.
  const res = await fetch("/api/stress/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      datasetId,
      scenario: { asset: "WETH", shockBps },
      agentRationale: rationale || "Phase 1 fixed scenario.",
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Stress test execution failed" }));
    throw new Error(err.detail || "Stress test execution failed");
  }
  return res.json();
}

export async function fetchFeed(since = 0, limit = 200): Promise<FeedResponse> {
  const res = await fetch(`${BACKEND_URL}/feed?since=${since}&limit=${limit}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Failed to load feed: HTTP ${res.status}`);
  return res.json();
}
