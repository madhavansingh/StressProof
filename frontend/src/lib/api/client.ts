/**
 * Backend API client for StressProof.
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

export async function fetchDatasets() {
  const res = await fetch(`${BACKEND_URL}/datasets`);
  if (!res.ok) throw new Error("Failed to load datasets");
  return res.json();
}

export async function runStressTest(datasetId: string, shockBps: number, rationale?: string) {
  const res = await fetch(`${BACKEND_URL}/stress/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_WRITE_TOKEN || "stressproof_dev_token_secret"}`,
    },
    body: JSON.stringify({
      datasetId,
      scenario: { asset: "WETH", shockBps },
      agentRationale: rationale,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Stress test execution failed");
  }
  return res.json();
}

export async function fetchFeed(since = 0) {
  const res = await fetch(`${BACKEND_URL}/feed?since=${since}`);
  if (!res.ok) throw new Error("Failed to load feed");
  return res.json();
}
